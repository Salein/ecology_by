"""Извлечение текста из HTML/TXT и чекбоксы из PDF."""
from __future__ import annotations

import re
from collections.abc import Callable

def _guess_part(filename: str, file_index: int) -> int:
    fn = filename.casefold().replace(" ", "")
    if "частьii" in fn or "часть2" in fn or "part2" in fn or fn.endswith("ii.pdf"):
        return 2
    if "ii)" in fn or "_ii." in fn or "-ii." in fn:
        return 2
    if file_index == 0:
        return 1
    return 2


def _extract_accepts_external_by_object_id(
    pdf_bytes: bytes,
    *,
    page_progress: Callable[[int, int], None] | None = None,
) -> dict[int, bool]:
    """
    Извлекает флаг "принимает от других" из чекбоксов PDF:
    - колонка 1: "Использует собственные"
    - колонка 2: "Принимает от других"
    Вектора чекбоксов в реестре стабильно стоят в правой части страницы
    (x ~ 700 и x ~ 754 для landscape-страниц ecoinfo).
    """
    try:
        import fitz
    except Exception:
        return {}

    out: dict[int, bool] = {}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return {}

    try:
        tot_pages = int(doc.page_count)
        for pi in range(tot_pages):
            if page_progress is not None and pi % 20 == 0:
                page_progress(pi + 1, tot_pages)
            page = doc.load_page(pi)
            words = page.get_text("words") or []
            if not words:
                continue

            object_rows: list[tuple[int, float]] = []
            for w in words:
                tok = str(w[4] or "").strip()
                if tok != "Объект":
                    continue
                y = float(w[1])
                x = float(w[0])
                candidates: list[tuple[float, int]] = []
                for w2 in words:
                    t2 = str(w2[4] or "").strip()
                    if not t2.isdigit():
                        continue
                    if not (1 <= len(t2) <= 6):
                        continue
                    if float(w2[0]) <= x + 10:
                        continue
                    if abs(float(w2[1]) - y) > 3.5:
                        continue
                    try:
                        val = int(t2)
                    except ValueError:
                        continue
                    # Номер объекта в реестре обычно в левой части строки.
                    if val < 1 or val > 999999:
                        continue
                    candidates.append((float(w2[0]), val))
                # В части II ID часто вынесен на отдельную строку чуть выше метки "Объект".
                # Если на той же строке ID нет — ищем ближайший короткий numeric-token сверху.
                if not candidates:
                    vertical: list[tuple[float, float, int]] = []
                    for w2 in words:
                        t2 = str(w2[4] or "").strip()
                        if not t2.isdigit() or not (1 <= len(t2) <= 6):
                            continue
                        yy = float(w2[1])
                        xx = float(w2[0])
                        if yy > y + 1.0:
                            continue
                        if y - yy > 90.0:
                            continue
                        if xx > 280.0:
                            continue
                        try:
                            val = int(t2)
                        except ValueError:
                            continue
                        if val < 1 or val > 999999:
                            continue
                        vertical.append((y - yy, xx, val))
                    if vertical:
                        vertical.sort(key=lambda item: (item[0], item[1]))
                        candidates.append((x + 1.0, int(vertical[0][2])))
                if not candidates:
                    continue
                candidates.sort(key=lambda item: item[0])
                object_rows.append((candidates[0][1], y))

            if not object_rows:
                continue

            drawings = page.get_drawings() or []
            marks: list[tuple[float, float]] = []
            for it in drawings:
                r = it.get("rect")
                if not r:
                    continue
                w = float(r.x1 - r.x0)
                h = float(r.y1 - r.y0)
                # Маркер "галочки" в этом PDF — stroke-элемент внутри квадрата (примерно 5x4).
                if it.get("type") != "s":
                    continue
                if not (2.0 <= w <= 7.2 and 2.0 <= h <= 7.2):
                    continue
                cx = float((r.x0 + r.x1) / 2.0)
                cy = float((r.y0 + r.y1) / 2.0)
                marks.append((cx, cy))

            for obj_id, y in object_rows:
                first_mark = False
                second_mark = False
                for cx, cy in marks:
                    if abs(cy - (y + 4.5)) > 7.0:
                        continue
                    if 697.0 <= cx <= 706.5:
                        first_mark = True
                    if 751.0 <= cx <= 760.5:
                        second_mark = True

                if not first_mark and not second_mark:
                    continue
                # При спорном случае (обе) считаем, что "принимает от других" отмечено.
                out[obj_id] = bool(second_mark)
    finally:
        doc.close()

    return out


def _extract_text_from_html_or_txt_bytes(raw: bytes) -> str:
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = raw.decode("cp1251", errors="ignore")
    txt = re.sub(r"(?is)<script.*?>.*?</script>", " ", txt)
    txt = re.sub(r"(?is)<style.*?>.*?</style>", " ", txt)
    txt = re.sub(r"(?is)<[^>]+>", " ", txt)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&")
    return " ".join(txt.split())
