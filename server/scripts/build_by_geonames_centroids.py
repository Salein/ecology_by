"""
Скачивает GeoNames BY.zip и собирает app/data/by_geonames_centroids.json
для офлайн-оценки координат по названию НП (деревни, агрогородки и т.д.).

Данные: https://www.geonames.org/ (Creative Commons Attribution 4.0).
Запуск из каталога server: python scripts/build_by_geonames_centroids.py
"""

from __future__ import annotations

import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

URL = "https://download.geonames.org/export/dump/BY.zip"
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "by_geonames_centroids.json"

# Минимальная длина токена — меньше даёт ложные вхождения в чужие строки
MIN_LEN = 4
# Не брать «имена» из alternatenames, похожие на служебный мусор
_SKIP_ALT_RE = re.compile(r"^\d+$|^[A-Z]{2,3}\d+$|^https?:")


def _clean_name(s: str) -> str | None:
    s = (s or "").strip().casefold().replace("\xa0", " ")
    if len(s) < MIN_LEN or _SKIP_ALT_RE.search(s):
        return None
    # только буквы/цифры/дефис/апостроф (кириллица + латиница)
    if not re.match(r"^[\w\-\']+$", s, flags=re.UNICODE):
        return None
    return s.replace("-", " ")


def main() -> None:
    print("download", URL)
    raw = urllib.request.urlopen(URL, timeout=120).read()
    zf = zipfile.ZipFile(io.BytesIO(raw))
    by_txt = next(n for n in zf.namelist() if n.endswith("BY.txt"))
    text = zf.read(by_txt).decode("utf-8", errors="replace")

    # name -> (lat, lon, pop) лучший по численности при коллизии
    best: dict[str, tuple[float, float, int]] = {}

    def consider(key: str | None, la: float, lo: float, pop: int) -> None:
        if not key:
            return
        prev = best.get(key)
        if prev is None or pop > prev[2]:
            best[key] = (la, lo, pop)

    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 15:
            continue
        if parts[6] != "P":
            continue
        name, _ascii, alts = parts[1], parts[2], parts[3]
        try:
            la, lo = float(parts[4]), float(parts[5])
        except ValueError:
            continue
        try:
            pop = int(parts[14] or 0)
        except ValueError:
            pop = 0

        for chunk in [name, _ascii, *alts.split(",")]:
            ck = _clean_name(chunk.strip())
            consider(ck, la, lo, pop)

    out_map: dict[str, list[float]] = {k: [v[0], v[1]] for k, v in best.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_map, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("written", OUT, "keys", len(out_map), "size_kb", round(OUT.stat().st_size / 1024, 1))


if __name__ == "__main__":
    main()
