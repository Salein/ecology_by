"""OCR изображений реестра и эвристики чекбоксов по OCR-тексту."""
from __future__ import annotations

import io
import re

def _ocr_text_score(text: str) -> int:
    s = text or ""
    if not s.strip():
        return -10_000
    score = 0
    score += min(60, len(s) // 220)
    score += len(re.findall(r"(?m)^\s*\d{7}(?!\d)", s)) * 90
    score += len(re.findall(r"(?im)\bОбъект\s*(?:№\.?)?\s*\d{1,5}\b", s)) * 45
    score += len(re.findall(r"(?im)\bСобственник\b", s)) * 30
    score += len(re.findall(r"\b\d{6}\b", s)) * 8
    # Много вопросиков/мусора обычно значит плохое качество OCR.
    score -= len(re.findall(r"[?]{2,}", s)) * 6
    return score


def _extract_text_from_image_bytes(raw: bytes) -> str:
    try:
        from PIL import Image, ImageFilter, ImageOps
        import pytesseract
    except Exception as e:
        raise RuntimeError(
            "OCR не настроен: установите зависимости Pillow + pytesseract и бинарник Tesseract OCR."
        ) from e
    with Image.open(io.BytesIO(raw)) as base_img:
        # OCR быстрее и стабильнее на нормализованном grayscale и с адаптацией масштаба.
        img = ImageOps.exif_transpose(base_img)
        if img.mode != "L":
            img = img.convert("L")
        max_side = max(img.size)
        # Для страниц реестра с мелким шрифтом лучше слегка увеличить, а не только downscale.
        target_side = 2600
        if max_side < 1700:
            scale = min(2.0, target_side / float(max_side))
            new_size = (
                max(1, int(round(img.size[0] * scale))),
                max(1, int(round(img.size[1] * scale))),
            )
            img = img.resize(new_size)
        elif max_side > target_side:
            scale = target_side / float(max_side)
            new_size = (
                max(1, int(round(img.size[0] * scale))),
                max(1, int(round(img.size[1] * scale))),
            )
            img = img.resize(new_size)

        base = ImageOps.autocontrast(img)
        sharpened = base.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=3))
        binary = sharpened.point(lambda p: 255 if p >= 168 else 0, mode="1").convert("L")

        variants = [base, sharpened, binary]
        # Для табличных сканов реестра psm 4/6 обычно лучше, но иногда psm 11 вытягивает разреженные строки.
        configs = ("--oem 1 --psm 6", "--oem 1 --psm 4", "--oem 1 --psm 11")

        best_txt = ""
        best_score = -10_000
        for v in variants:
            for cfg in configs:
                txt = pytesseract.image_to_string(v, lang="rus+eng", config=cfg) or ""
                sc = _ocr_text_score(txt)
                if sc > best_score:
                    best_score = sc
                    best_txt = txt
    return best_txt or ""


_OCR_BOX_TOKEN_RE = re.compile(r"\[(?:\s|x|X|х|Х|v|V|\+|\*)\]")
_OCR_OBJ_ID_RE = re.compile(r"(?i)\bОбъект\s*(?:№\.?)?\s*(\d{1,6})")


def _extract_accepts_external_from_ocr_text(text: str) -> dict[int, bool]:
    """
    Грубая эвристика для изображений (JPEG/PNG/...):
    пытаемся считать пару чекбоксов в строке «Объект ...».
    Возвращаем только уверенные попадания; остальным оставляем parser default.
    """
    src = (text or "").replace("\xa0", " ")
    if not src.strip():
        return {}

    lines = [ln.strip() for ln in src.splitlines() if ln.strip()]
    out: dict[int, bool] = {}

    def _pair_from_text(chunk: str) -> bool | None:
        s = re.sub(r"\s+", " ", chunk or "")
        if not s:
            return None
        ballots = re.findall(r"[\u2610\u2611\u2612]", s)
        if len(ballots) >= 2:
            second = ballots[-1]
            if second == "\u2610":
                return False
            if second in ("\u2611", "\u2612"):
                return True
        boxes = _OCR_BOX_TOKEN_RE.findall(s)
        if len(boxes) >= 2:
            second = boxes[-1].strip().strip("[]").strip().casefold()
            return second in {"x", "х", "v", "+", "*"}
        # OCR иногда даёт "не принимает от других"/"принимает от других" вместо символов чекбокса.
        if re.search(r"(?i)\bне\s+принимает\s+(?:отходы?\s+)?от\s+других\b", s):
            return False
        if re.search(r"(?i)\bпринимает\s+(?:отходы?\s+)?от\s+других\b", s):
            return True
        return None

    for i, line in enumerate(lines):
        m = _OCR_OBJ_ID_RE.search(line)
        if not m:
            continue
        try:
            obj_id = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if obj_id <= 0:
            continue
        chunk = " ".join(lines[i : min(len(lines), i + 3)])
        inferred = _pair_from_text(chunk)
        if inferred is None:
            continue
        out[obj_id] = bool(inferred)
    return out
