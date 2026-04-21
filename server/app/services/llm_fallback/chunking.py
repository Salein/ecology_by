from __future__ import annotations

import re

_NOISE_LINE_RE = re.compile(
    r"^\s*(?:Страница\s+\d+\s*(?:из\s*\d+)?|Использует\s+собственные|Принимает\s+от\s+других)\s*$",
    re.IGNORECASE,
)
_WASTE_CODE_START_RE = re.compile(r"^\s*\d{7}\s+")


def split_into_record_chunks(text: str, records_per_chunk: int = 2) -> list[str]:
    lines = [ln.strip() for ln in (text or "").replace("\xa0", " ").splitlines() if ln.strip()]
    lines = [ln for ln in lines if not _NOISE_LINE_RE.match(ln)]
    if not lines:
        return []

    segments: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _WASTE_CODE_START_RE.match(line) and current:
            segments.append(current)
            current = [line]
            continue
        current.append(line)
    if current:
        segments.append(current)

    if not segments:
        return []

    per = max(1, int(records_per_chunk))
    out: list[str] = []
    for i in range(0, len(segments), per):
        group = segments[i : i + per]
        out.append("\n---NEXT_RECORD---\n".join("\n".join(s) for s in group))
    return out
