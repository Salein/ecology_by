"""
Оценка числа записей реестра в папке с изображениями (JPEG/PNG/…).

Использует тот же OCR и парсер, что импорт реестра (см. registry_import_jobs / registry_record_parser).

Пример (Docker, Windows):
  docker compose run --rm --no-deps ^
    -v "E:/весь реестр в сборе:/reg:ro" ^
    -v "%CD%/server:/srv:ro" ^
    api sh -c "PYTHONPATH=/srv python /srv/scripts/count_registry_images_estimate.py /reg"

Полный проход по всем файлам: добавьте --full (может занять много часов).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

# Запуск из смонтированного /srv: пакет app лежит в /srv/app
if __name__ == "__main__" and (srv := Path(__file__).resolve().parent.parent) and (srv / "app").is_dir():
    sys.path.insert(0, str(srv))

from app.services.registry_import.ocr import _extract_text_from_image_bytes  # noqa: E402
from app.services.registry_record_parser import (  # noqa: E402
    iter_registry_plain_text,
    preprocess_registry_plaintext,
)


def _guess_part(name: str) -> int:
    fn = name.casefold().replace(" ", "")
    if "частьii" in fn or "часть2" in fn or "part2" in fn or fn.endswith("ii.jpg"):
        return 2
    if "ii)" in fn or "_ii." in fn or "-ii." in fn:
        return 2
    return 1


def _collect_images(root: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in exts:
            out.append(p)
    out.sort(key=lambda x: (str(x.parent), x.name.casefold()))
    return out


def _count_rows_in_image(path: Path) -> int:
    raw = path.read_bytes()
    text = _extract_text_from_image_bytes(raw)
    text = preprocess_registry_plaintext(text)
    part = _guess_part(path.name)
    return sum(1 for _ in iter_registry_plain_text(text, part, text_preprocessed=True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path, help="Корневая папка с изображениями")
    ap.add_argument(
        "--sample",
        type=int,
        default=48,
        help="Сколько файлов равномерно выбрать для оценки (игнорируется при --full)",
    )
    ap.add_argument("--full", action="store_true", help="Обработать все файлы (долго)")
    args = ap.parse_args()

    root = args.folder.resolve()
    if not root.is_dir():
        print(f"Не папка: {root}", file=sys.stderr)
        return 2

    files = _collect_images(root)
    n = len(files)
    print(f"Файлов изображений: {n}")
    if n == 0:
        return 0

    if args.full:
        indices = list(range(n))
    else:
        k = max(1, min(args.sample, n))
        if k == 1:
            indices = [0]
        else:
            indices = [int(round(i * (n - 1) / (k - 1))) for i in range(k)]

    counts: list[int] = []
    errs = 0
    for i in indices:
        p = files[i]
        try:
            c = _count_rows_in_image(p)
            counts.append(c)
            print(f"[{len(counts)}/{len(indices)}] {p.name}: {c} записей")
        except Exception as e:
            errs += 1
            print(f"ERR {p}: {e}", file=sys.stderr)

    if not counts:
        print("Не удалось посчитать ни один файл.", file=sys.stderr)
        return 1

    total_sample = sum(counts)
    avg = total_sample / len(counts)
    if args.full:
        print(f"ИТОГО записей (полный проход): {total_sample}")
        if errs:
            print(f"Ошибок файлов: {errs}", file=sys.stderr)
        return 0

    est = int(round(avg * n))
    med = float(statistics.median(counts)) if len(counts) >= 2 else float(counts[0])
    est_med = int(round(med * n))
    print(
        f"Выборка: {len(counts)} файлов, сумма строк в выборке={total_sample}, "
        f"среднее на файл={avg:.2f}, медиана на файл={med:.2f}"
    )
    print(f"ОЦЕНКА всего набора (~{n} файлов): по среднему ≈ {est} записей, по медиане ≈ {est_med} записей")
    print("(Оценка приблизительная: разные страницы дают разное число строк; полный подсчёт: --full)")
    if errs:
        print(f"Ошибок файлов: {errs}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
