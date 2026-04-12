"""
Парсинг текста PDF «Реестр объектов по использованию отходов» (части I и II), ecoinfo.by.

Формат: блоки по коду ФККО (7 цифр), внутри — одна или несколько карточек «Объект …» / «Собственник …».
"""

from __future__ import annotations

import re
from typing import Any

CODE_START = re.compile(r"^(\d{7})\s+(.*)$")
OBJECT_START = re.compile(r"^Объект\s*(\d+)\s*(.*)$")
OWNER_START = re.compile(r"^Собственник\s*(.*)$")
POSTAL = re.compile(r"\b(\d{6}),\s*")
ADDR_UL = re.compile(r"\d{6},\s*ул\.")


def _trim_tail_noise(s: str) -> str:
    s = s.strip()
    for pat in (
        r"\s+тел\.?\s*.*$",
        r"\s+\(?0\d{3,4}\)?.*$",
        r"\s+8-0\d{2,3}.*$",
        r"\s+\d{8,}.*$",  # длинные «номера» в конце строки
    ):
        s = re.split(pat, s, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return s


def extract_name_address_multiline(blob: str) -> tuple[str, str]:
    """
    Делит текст карточки (несколько строк) на наименование объекта/собственника и адрес для геокодера.
    Строка с «######, ул.» (или индекс с 12+ позиции) начинает адрес; дальнейшие строки с признаками
    адреса идут в адрес, остальные — обратно в наименование (типично для PDF БелНИЦ).
    """
    raw = [ln.strip() for ln in blob.replace("\xa0", " ").splitlines() if ln.strip()]
    name_parts: list[str] = []
    addr_parts: list[str] = []
    phase = "before"

    for line in raw:
        if line.startswith("Собственник"):
            break
        ul_m = ADDR_UL.search(line)
        idx_m = POSTAL.search(line)
        if phase == "before" and ul_m:
            head = line[: ul_m.start()].strip()
            tail = line[ul_m.start() :].strip()
            if head:
                name_parts.append(head)
            addr_parts.append(tail)
            phase = "after_addr"
            continue
        if phase == "before" and idx_m and idx_m.start() >= 12:
            head = line[: idx_m.start()].strip()
            tail = line[idx_m.start() :].strip()
            if head:
                name_parts.append(head)
            addr_parts.append(tail)
            phase = "after_addr"
            continue
        if phase == "after_addr":
            low = line.casefold()
            addr_hints = (
                "обл.",
                "р-н",
                "с/с",
                "ул.",
                "улица",
                "д.",
                "г.",
                "пер.",
                "просп.",
                "дер.",
                "д.",
                "республика",
                "область",
            )
            if any(h in low for h in addr_hints) or POSTAL.search(line):
                addr_parts.append(line)
            else:
                name_parts.append(line)
        else:
            name_parts.append(line)

    name = re.sub(r"\s+", " ", " ".join(name_parts)).strip()
    address = re.sub(r"\s+", " ", " ".join(addr_parts)).strip()
    address = _trim_tail_noise(address)
    if not name:
        name = re.sub(r"\s+", " ", blob).strip()[:240]
    return name, address


def clean_owner_blob(blob: str) -> str:
    blob = blob.replace("\xa0", " ").strip()
    blob = _trim_tail_noise(blob)
    return re.sub(r"\s+", " ", blob).strip()


def owner_display_name(owner_blob: str) -> str:
    name, _addr = extract_name_address_multiline(owner_blob)
    if len(name) >= 10:
        return name
    return clean_owner_blob(owner_blob)


def extract_phones_from_text(*blobs: str) -> str:
    """Выделяет телефоны/факс из сырого текста карточек объекта и собственника (реестр ecoinfo)."""
    text = "\n".join(b for b in blobs if b)
    if not text.strip():
        return ""
    patterns = [
        r"\(?0\d{2,4}\)?\s*[\d\s\-–]{5,}(?:\s*,\s*[\d\s\-–]{3,})*",
        r"8-\d{2,4}(?:-\d{2,}){2,}",
        r"(?:тел\.?|факс)\s*[:\.]?\s*[\d\s\-–,\(\)]+",
        r"(?<!\d)(?:\+?375|80)\d{9}(?!\d)",
        r"(?<!\d)\d{11}(?!\d)",
    ]
    seen_keys: set[str] = set()
    out: list[str] = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            s = re.sub(r"\s+", " ", m.group(0).strip()).rstrip(".,;")
            if len(s) < 5:
                continue
            digits = re.sub(r"\D+", "", s)
            if len(digits) < 5:
                continue
            if digits in seen_keys:
                continue
            seen_keys.add(digits)
            out.append(s)
            if len(out) >= 12:
                return "; ".join(out)
    return "; ".join(out)


def parse_registry_plain_text(full_text: str, source_part: int) -> list[dict[str, Any]]:
    lines = full_text.splitlines()
    while lines and not CODE_START.match(lines[0].strip()):
        lines.pop(0)

    segments: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        st = line.strip()
        if CODE_START.match(st) and cur:
            segments.append(cur)
            cur = [line]
        elif CODE_START.match(st) and not cur:
            cur = [line]
        else:
            cur.append(line)
    if cur:
        segments.append(cur)

    out: list[dict[str, Any]] = []
    for seg in segments:
        if not seg:
            continue
        first = seg[0].strip()
        m0 = CODE_START.match(first)
        if not m0:
            continue
        waste_code = m0.group(1)
        wtail = m0.group(2).strip()
        rest = [x.strip() for x in seg[1:]]
        wname_parts = [wtail]
        i = 0
        while i < len(rest):
            if OBJECT_START.match(rest[i]):
                break
            wname_parts.append(rest[i])
            i += 1
        waste_type_name = " ".join(x for x in wname_parts if x).strip()
        remainder = rest[i:]

        j = 0
        while j < len(remainder):
            om = OBJECT_START.match(remainder[j])
            if not om:
                j += 1
                continue
            reg_id = int(om.group(1))
            tail = om.group(2).strip()
            j += 1
            obj_chunks = [tail]
            while j < len(remainder):
                nxt = remainder[j]
                stn = nxt.strip()
                if OBJECT_START.match(stn) or CODE_START.match(stn):
                    break
                if OWNER_START.match(stn):
                    break
                obj_chunks.append(stn)
                j += 1
            object_blob = "\n".join(x for x in obj_chunks if x).strip()

            if j >= len(remainder):
                break
            owm = OWNER_START.match(remainder[j].strip())
            if not owm:
                continue
            own_tail = owm.group(1).strip()
            j += 1
            own_chunks = [own_tail]
            while j < len(remainder):
                stn = remainder[j].strip()
                if OBJECT_START.match(stn) or CODE_START.match(stn):
                    break
                own_chunks.append(stn)
                j += 1
            owner_blob = "\n".join(x for x in own_chunks if x).strip()

            object_name, addr_obj = extract_name_address_multiline(object_blob)
            owner_name = owner_display_name(owner_blob)
            _oname2, addr_own = extract_name_address_multiline(owner_blob)
            address = addr_obj or addr_own or owner_blob
            address = _trim_tail_noise(address)
            if len(address) < 8:
                address = addr_obj or addr_own or owner_blob

            phones = extract_phones_from_text(object_blob, owner_blob)

            out.append(
                {
                    "id": reg_id,
                    "owner": owner_name,
                    "object_name": object_name or object_blob[:200],
                    "waste_code": waste_code,
                    "waste_type_name": waste_type_name,
                    "accepts_external_waste": True,
                    "address": address,
                    "phones": phones,
                    "source_part": source_part,
                }
            )
    return out
