"""
Парсинг текста PDF «Реестр объектов по использованию отходов» (части I и II), ecoinfo.by.

Формат: блоки по коду ФККО (7 цифр), внутри — одна или несколько карточек «Объект …» / «Собственник …».
"""

from __future__ import annotations

import re
from typing import Any, Iterator

# Код ФККО — ровно 7 цифр; дальше не должна идти ещё одна цифра (иначе это не начало блока).
# Разбор начала строки — в _fkko_line_parts (учёт префиксов таблицы и пробелов между цифрами).
OBJECT_START = re.compile(
    r"^(?:Объект|[Oo]bject)\s*(?:№\.?)?\s*(\d+)\s*(.*)$",
    re.IGNORECASE,
)
OWNER_START = re.compile(r"^Собственник\s*(.*)$", re.IGNORECASE)

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_LEADING_LINE_JUNK = re.compile(
    r"^[\s|.:;\t\[({№#»\"'+\-\\/‐‑–—]+",
)


def _fkko_line_parts(st: str) -> tuple[str, str] | None:
    """
    Строка начала блока ФККО: допускает префиксы из PDF-таблицы и пробелы между цифрами кода.
    """
    raw = (st or "").strip().translate(_FULLWIDTH_DIGITS)
    if not raw:
        return None
    s = _LEADING_LINE_JUNK.sub("", raw)
    if not s:
        return None
    m_sp = re.match(r"^((?:\d)(?:[\s\u00a0]+\d){6})(\s*)(.*)$", s)
    if m_sp:
        tail_after = (m_sp.group(3) or "").lstrip()
        if tail_after[:1].isdigit():
            pass
        else:
            code = re.sub(r"[\s\u00a0]+", "", m_sp.group(1))
            if len(code) == 7 and code.isdigit():
                rest = ((m_sp.group(2) or "") + (m_sp.group(3) or "")).strip()
                return code, rest
    m = re.match(r"^(\d{7})(?!\d)\s*(.*)$", s)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    return None


POSTAL = re.compile(r"\b(\d{6}),\s*")
ADDR_UL = re.compile(r"\d{6},\s*ул\.")
ADDR_HINT = re.compile(
    r"\b(ул\.|улица|пер\.|просп\.|б-р|шоссе|аг\.|д\.|дер\.)\s*[^,;]+(?:,\s*[^,;]+){0,3}",
    re.IGNORECASE,
)

_OBJECT_FIELD_NOISE_LINE_RE = re.compile(
    r"^\s*(?:"
    r"объекты?\s*,?\s*которые\s+принимают\s+отходы?\s+от\s+других(?:\s+лиц)?"
    r"|принимает\s+отходы?\s+от\s+других(?:\s+лиц)?"
    r"|использует\s+собственные\s+отходы?"
    r"|объект(?:ы)?"
    r")\s*$",
    flags=re.IGNORECASE,
)
_OBJECT_CANON_HINT_RE = re.compile(
    r"\b(?:мобильн\w*|стационарн\w*|дробильн\w*|сортировочн\w*|установк\w*|комплекс\w*|линия|цех|пункт|участок)\b",
    flags=re.IGNORECASE,
)
_INLINE_OWNER_SPLIT_RE = re.compile(r"(?i)\bСобственник\b")
_ADDRESS_HINT_LINE_RE = re.compile(
    r"\b(?:обл\.|р-н|с/с|ул\.|улица|д\.|г\.|пер\.|просп\.|дер\.|республика|область|шоссе|б-р)\b",
    flags=re.IGNORECASE,
)
_PHONE_OR_FAX_RE = re.compile(
    r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\bтел\.?\b|\bфакс\b)",
    flags=re.IGNORECASE,
)

_TRAILING_CITY_WORD_RE = re.compile(r"\b([А-ЯЁ][а-яё\-]{2,})\s*$")
_CITY_STOPWORDS = {
    "ООО",
    "ОАО",
    "ЗАО",
    "УП",
    "РУП",
    "ЧУП",
    "КУП",
    "ГУ",
    "ГУП",
    "КПУП",
    "КХП",
}


def _is_object_field_noise_line(line: str) -> bool:
    s = re.sub(r"\s+", " ", (line or "").replace("\xa0", " ")).strip(" ,;:.")
    if not s:
        return True
    return bool(_OBJECT_FIELD_NOISE_LINE_RE.fullmatch(s))


def _select_canonical_object_name(blob: str, waste_type_name: str) -> str:
    """
    Выбирает наиболее информативное название объекта из строк object_blob:
    приоритет — строки с признаками оборудования/объекта.
    """
    candidates: list[str] = []
    for ln in (blob or "").replace("\xa0", " ").splitlines():
        s = re.sub(r"\s+", " ", ln).strip()
        if not s:
            continue
        if _is_object_field_noise_line(s):
            continue
        if re.search(r"\b\d{6}\b", s):
            continue
        cleaned = _clean_object_name_final(s, waste_type_name)
        if cleaned:
            candidates.append(cleaned)
    if not candidates:
        return ""

    def _object_line_score(s: str) -> int:
        score = 0
        if _OBJECT_CANON_HINT_RE.search(s):
            score += 70
        words = len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", s))
        score += min(18, words)
        score += min(12, len(s) // 14)
        # Штраф за служебный/нормативный хвост.
        if re.search(
            r"\b(?:в\s+соответствии|об\s+охране\s+окружающей\s+среды|использует|принимает|собственник|объект)\b",
            s,
            flags=re.IGNORECASE,
        ):
            score -= 45
        # Штраф за "общие" площадки/участки без конкретики оборудования.
        if re.search(r"\b(?:площадка\s+по|место\s+складирования)\b", s, flags=re.IGNORECASE):
            score -= 16
        return score

    ranked = sorted(candidates, key=lambda x: (-_object_line_score(x), -len(x), x.casefold()))
    return ranked[0]


_NAME_FINAL_STRIP = " ,;:.«»*-–—"


def _normalize_phrase_dashes(s: str) -> str:
    """Типографские тире и ASCII-дефис только как разделитель (с пробелами) → пробел; составные «слово-слово» сохраняем."""
    s = re.sub(r"\s*[—–]\s*", " ", s)
    return re.sub(r"\s+-\s+", " ", s)


def _clean_object_name_final(name: str, waste_type_name: str = "") -> str:
    """
    Финальная чистка названия объекта:
    - убирает служебные фразы реестра;
    - отрезает длинные юр-хвосты собственника;
    - убирает префикс вида отхода, если он попал в object_name.
    """
    s = re.sub(r"\s+", " ", (name or "").replace("\xa0", " ")).strip(" ,;:.")
    s = re.sub(r"[`´‘’“”]", '"', s)
    s = _normalize_phrase_dashes(s)
    if not s:
        return ""
    s_initial = s

    s = re.sub(r"объекты?\s*,?\s*которые\s+принимают\s+отходы?\s+от\s+других(?:\s+лиц)?", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"принимает\s+отходы?\s+от\s+других(?:\s+лиц)?", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"использует\s+собственные\s+отходы?", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"^(?:от\s+других(?:\s+лиц)?[,:;\-–—\s]*)+", " ", s, flags=re.IGNORECASE)

    if waste_type_name:
        ws = re.sub(r"\s+", " ", waste_type_name.replace("\xa0", " ")).strip()
        if ws:
            s = re.sub(r"^" + re.escape(ws) + r"(?:[\s,;:.\\\-–—]+)?", "", s, flags=re.IGNORECASE)

    # Часто после реального названия объекта подмешивается хвост собственника.
    s = re.sub(r"(?:коммунальное|республиканское|государственное|частное)\s+унитарное\s+предприятие.*$", "", s, flags=re.IGNORECASE)
    s = re.sub(
        r"(?:коммунальное|республиканское|государственное|частное)\s+производственное\s+унитарное\s+предприятие.*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"(?:коммунальное|государственное)\s+предприятие.*$", "", s, flags=re.IGNORECASE)
    legal_tail = re.search(r"(^|[^A-Za-zА-Яа-яЁё])(?:ООО|ОАО|ЗАО|УП|РУП|ЧУП|ОДО|ИП)(?=$|[^A-Za-zА-Яа-яЁё])", s, flags=re.IGNORECASE)
    if legal_tail and legal_tail.start() > 12:
        s = s[: legal_tail.start()]
    cut_markers: list[int] = []
    m_postal = re.search(r"\b\d{6}\b", s)
    if m_postal and m_postal.start() > 8:
        cut_markers.append(m_postal.start())
    m_addr = re.search(r"\b(?:г\.|ул\.|улица|д\.|дом|обл\.|область|район|р-н|с/с)\b", s, flags=re.IGNORECASE)
    if m_addr and m_addr.start() > 12:
        cut_markers.append(m_addr.start())
    m_addr_ocr = re.search(
        r"\b(?:г\s+[А-ЯЁA-Z]|ул\s+[А-ЯЁA-Z]|пер\s+[А-ЯЁA-Z]|просп\s+[А-ЯЁA-Z])",
        s,
        flags=re.IGNORECASE,
    )
    if m_addr_ocr and m_addr_ocr.start() > 12:
        cut_markers.append(m_addr_ocr.start())
    m_phone = re.search(
        r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\bтел\.?\b|\bфакс\b)",
        s,
        flags=re.IGNORECASE,
    )
    if m_phone and m_phone.start() > 10:
        cut_markers.append(m_phone.start())
    if cut_markers:
        s = s[: min(cut_markers)]
    m_tail_addr = re.search(
        r"(?:,\s*|\s+)(?:г\.?|ул\.?|улица|д\.?|дом|обл\.?|область|район|р-н)\s+",
        s,
        flags=re.IGNORECASE,
    )
    if m_tail_addr and m_tail_addr.start() > 12:
        s = s[: m_tail_addr.start()]
    # Частый OCR-кейс: объект и адрес склеены через запятую в одной строке.
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) >= 2:
            tail = ", ".join(parts[1:])
            if re.search(
                r"(?:\b\d{6}\b|\+?\s*375|\(\s*0\d{2,4}\s*\)|\bг\.?\b|\bул\.?\b|\bд\.?\b|\bобл\.?\b|\bр-н\b)",
                tail,
                flags=re.IGNORECASE,
            ):
                s = parts[0]

    s = re.sub(r"\s+", " ", s).strip(_NAME_FINAL_STRIP)
    if re.fullmatch(r"(?:—|-|объект(?:ы)?)", s, flags=re.IGNORECASE):
        return ""
    if len(s) < 3:
        # Если агрессивная чистка "съела" почти всё (частый OCR/моджибейк),
        # возвращаем исходный вариант после базовой нормализации пробелов/пунктуации.
        s_fallback = re.sub(r"\s+", " ", s_initial).strip(_NAME_FINAL_STRIP)
        return "" if len(s_fallback) < 3 else s_fallback
    return s


def _clean_owner_name_final(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").replace("\xa0", " ")).strip(" ,;:.")
    if not s:
        return ""
    s = re.sub(r"[`´‘’“”]", '"', s)
    s = _normalize_phrase_dashes(s)
    # Не допускаем адрес/телефон в колонке "Собственник".
    m_postal = re.search(r"\b\d{6}\b", s)
    if m_postal and m_postal.start() > 8:
        s = s[: m_postal.start()]
    m_addr = re.search(
        r"\b(?:г\.|ул\.|улица|д\.|дом|обл\.|область|район|р-н|аг\.|дер\.|пос\.|пер\.|просп\.|шоссе)\b",
        s,
        flags=re.IGNORECASE,
    )
    if m_addr and m_addr.start() > 14:
        s = s[: m_addr.start()]
    m_phone = re.search(
        r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\bтел\.?\b|\bфакс\b)",
        s,
        flags=re.IGNORECASE,
    )
    if m_phone and m_phone.start() > 8:
        s = s[: m_phone.start()]
    m_city_tail = re.search(
        r"\s+\bг\.?\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}\s*$",
        s,
        flags=re.IGNORECASE,
    )
    if m_city_tail and m_city_tail.start() > 12:
        s = s[: m_city_tail.start()]
    m_region_tail = re.search(
        r"\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\- ]+\s+(?:обл\.?|область)\s*$",
        s,
        flags=re.IGNORECASE,
    )
    if m_region_tail and m_region_tail.start() > 12:
        s = s[: m_region_tail.start()]
    if "," in s:
        left, right = s.split(",", 1)
        if len(left.strip()) >= 6 and re.search(r"(?:\b\d{6}\b|\bобл\.?\b|\bр-н\b|\bрайон\b|\bг\.?\b)", right, re.IGNORECASE):
            s = left
    s = re.sub(r"\s+", " ", s).strip(_NAME_FINAL_STRIP)
    if len(s) < 3:
        return ""
    return s


def _extract_trailing_city_word(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip(_NAME_FINAL_STRIP)
    if not s:
        return ""
    m = _TRAILING_CITY_WORD_RE.search(s)
    if not m:
        return ""
    city = (m.group(1) or "").strip()
    if not city:
        return ""
    if city.upper() in _CITY_STOPWORDS:
        return ""
    return city


def _strip_trailing_city_word(text: str, city: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip(_NAME_FINAL_STRIP)
    c = (city or "").strip()
    if not s or not c:
        return s
    if s.casefold().endswith((" " + c).casefold()):
        s = s[: -len(c)].strip(_NAME_FINAL_STRIP)
    return s


def _trim_tail_noise(s: str) -> str:
    s = s.strip()
    for pat in (
        # Колонтитул PDF реестра ecoinfo: дата + «Страница N из M»
        r"\s*\d{1,2}\s+[а-яё]+\s+\d{4}\s*г\.\s*Страница\s+\d+\s+из\s+\d+.*$",
        r"\s*Страница\s+\d+\s+из\s+\d+.*$",
        r"\s+тел\.?\s*.*$",
        r"\s+\(?0\d{3,4}\)?.*$",
        r"\s+8-0\d{2,3}.*$",
        r"\s+\d{8,}.*$",  # длинные «номера» в конце строки
    ):
        s = re.split(pat, s, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return s


def _extract_address_hint(s: str) -> str | None:
    text = re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()
    if not text:
        return None
    m = ADDR_HINT.search(text)
    if not m:
        return None
    hint = m.group(0)
    hint = re.sub(
        r"\b(предприятие|использует|принимает|объект(?:ы)?|собственник)\b.*$",
        "",
        hint,
        flags=re.IGNORECASE,
    ).strip()
    hint = re.sub(r"[,\s]+$", "", hint)
    return hint or None


_LOCALITY_RE = re.compile(
    r"\b(г\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|г/п\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|аг\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|д\.\s*[А-ЯЁA-ZА-ЯЁа-яё0-9][А-ЯЁA-Za-zа-яё0-9\-]+(?:\s+[А-ЯЁA-ZА-ЯЁа-яё0-9][А-ЯЁA-Za-zа-яё0-9\-]+){0,2}"
    r"|дер\.\s*[А-ЯЁA-ZА-ЯЁа-яё0-9][А-ЯЁA-Za-zа-яё0-9\-]+(?:\s+[А-ЯЁA-ZА-ЯЁа-яё0-9][А-ЯЁA-Za-zа-яё0-9\-]+){0,2}"
    r"|п\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|пос\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|пос[её]лок\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|городок\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2})\b",
    flags=re.IGNORECASE,
)
_STREET_RE = re.compile(
    r"\b(?:ул\.|улица|пер\.|просп\.|б-р|шоссе)\s*[^,;]{2,80}",
    flags=re.IGNORECASE,
)
_HOUSE_RE = re.compile(r"\b(?:д\.|дом)\s*\d+[A-Za-zА-Яа-я0-9/\-]*", flags=re.IGNORECASE)
_REGION_RE = re.compile(r"\b[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\- ]+\s+обл\.(?=[,\s]|$)", flags=re.IGNORECASE)
_DISTRICT_RE = re.compile(r"\b[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\- ]+\s+(?:р-н|район)\b", flags=re.IGNORECASE)
# «220030, Минск, ул. …» без префикса «г.» — для геокодера и address_no_locality.
# (?<!\d) вместо \b: граница слова перед цифрой в начале строки не срабатывает.
# Класс символов города — через Unicode-диапазоны (устойчивее к homoglyph в исходнике).
_CYR_LET_CLASS = r"\u0410-\u042f\u0430-\u044f\u0401\u0451"
_BARE_LOCALITY_AFTER_POSTAL_RE = re.compile(
    rf"(?<!\d)(\d{{6}})\s*,\s*"
    rf"([{_CYR_LET_CLASS}A-Z][{_CYR_LET_CLASS}A-Za-z\-\s]{{2,45}}?)\s*,\s*"
    r"(?=(?:\u0443\u043b\.|\u0443\u043b\u0438\u0446\u0430|\u043f\u0435\u0440\.|\u043f\u0440\u043e\u0441\u043f\.|"
    r"\u0431\u002d\u0440|\u0448\u043e\u0441\u0441\u0435|\u0434\.|\u0434\u043e\u043c))",
    flags=re.IGNORECASE,
)


def _normalize_bare_locality_after_postal(address: str) -> str:
    if not address or _LOCALITY_RE.search(address):
        return address

    def repl(m: re.Match[str]) -> str:
        post, city = m.group(1), re.sub(r"\s+", " ", (m.group(2) or "").strip())
        if not city or re.match(r"г\.", city, flags=re.IGNORECASE):
            return m.group(0)
        if re.search(r"\b(?:обл\.|р-н|район|область)\b", city, flags=re.IGNORECASE):
            return m.group(0)
        if re.fullmatch(r"\d+", city):
            return m.group(0)
        return f"{post}, г. {city}, "

    return _BARE_LOCALITY_AFTER_POSTAL_RE.sub(repl, address)


def _merge_split_phone_lines(text: str) -> str:
    """Склеивает номер, разорванный переносом строки (частый артефакт PDF)."""
    lines = (text or "").replace("\xa0", " ").splitlines()
    if len(lines) < 2:
        return text
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i].rstrip()
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            merge = False
            if re.search(r"\+?\s*375\s*$", cur) and re.match(r"^[\s\(]*\d", nxt):
                merge = True
            elif re.search(r"\(\s*0\d{2,4}\s*\)\s*$", cur) and re.match(r"^[\d\s\-–]{4,}", nxt):
                merge = True
            elif re.search(r"(?i)(?:тел\.?|моб\.?|сот\.?|факс)\s*:?\s*$", cur) and re.match(
                r"^[\d\s\+\(\)\-–]{5,}", nxt
            ):
                merge = True
            if merge:
                out.append(f"{cur} {nxt}")
                i += 2
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _extract_address_components(address: str) -> dict[str, str]:
    s = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip(" ,;")
    if not s:
        return {"postal": "", "locality": "", "region": "", "district": "", "street": "", "house": "", "raw": ""}
    pm = re.search(r"\b(\d{6})\b", s)
    lm = _LOCALITY_RE.search(s)
    sm = _STREET_RE.search(s)
    hm = _HOUSE_RE.search(s)
    rm = _REGION_RE.search(s)
    dm = _DISTRICT_RE.search(s)
    return {
        "postal": pm.group(1) if pm else "",
        "locality": re.sub(r"\s+", " ", lm.group(1)).strip(" ,;") if lm else "",
        "region": re.sub(r"\s+", " ", rm.group(0)).strip(" ,;") if rm else "",
        "district": re.sub(r"\s+", " ", dm.group(0)).strip(" ,;") if dm else "",
        "street": re.sub(r"\s+", " ", sm.group(0)).strip(" ,;") if sm else "",
        "house": re.sub(r"\s+", " ", hm.group(0)).strip(" ,;") if hm else "",
        "raw": s,
    }


def _canonicalize_address_from_components(address: str) -> str:
    c = _extract_address_components(address)
    if not c["raw"]:
        return ""
    parts: list[str] = []
    if c["postal"]:
        parts.append(c["postal"])
    if c["locality"]:
        parts.append(c["locality"])
    if c["district"]:
        parts.append(c["district"])
    if c["region"]:
        parts.append(c["region"])
    if c["street"]:
        parts.append(c["street"])
    if c["house"]:
        # Don't duplicate house if it is already inside street segment.
        if c["house"].casefold() not in c["street"].casefold():
            parts.append(c["house"])
    if not parts:
        return c["raw"]
    out = ", ".join(parts)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"[,\s]+$", "", out).strip()
    return out or c["raw"]


def _dedupe_locality_in_address(address: str) -> str:
    """
    Убирает повтор одного и того же населённого пункта в адресе.
    Частый артефакт: "..., г. Гомель, ..., г. Гомель".
    """
    compact = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip()
    if not compact:
        return compact
    matches = list(_LOCALITY_RE.finditer(compact))
    if len(matches) <= 1:
        return compact

    first = matches[0].group(1)
    first_norm = re.sub(r"\s+", " ", first).strip().casefold()
    if not first_norm:
        return compact

    # Удаляем повторные вхождения того же locality (по нормализованному виду).
    out_parts: list[str] = []
    last = 0
    kept_first = False
    for m in matches:
        loc = m.group(1)
        loc_norm = re.sub(r"\s+", " ", loc).strip().casefold()
        if not kept_first:
            kept_first = True
            continue
        if loc_norm == first_norm:
            out_parts.append(compact[last : m.start()])
            last = m.end()
    out_parts.append(compact[last:])
    out = "".join(out_parts)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r"[,\s]+$", "", out).strip()
    return out or compact


def _dedupe_consecutive_comma_segments(address: str) -> str:
    """
    Схлопывает подряд идущие одинаковые части между запятыми.
    Типичный артефакт PDF: «220020, г. Минск, г. Минск, г. Минск, ул. …».
    """
    s = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip()
    if not s or "," not in s:
        return s
    raw = [p.strip() for p in s.split(",")]
    out: list[str] = []
    for p in raw:
        if not p:
            continue
        key = re.sub(r"\s+", " ", p).strip().casefold()
        if out and re.sub(r"\s+", " ", out[-1]).strip().casefold() == key:
            continue
        out.append(p.strip())
    return ", ".join(out)


def _clean_address_noise_final(address: str) -> str:
    """
    Финальная чистка адреса от артефактов:
    - телефонные хвосты в конце адреса;
    - дубли населённого пункта в списке сегментов;
    - "г. (не указано)" при наличии реального города/НП.
    """
    s = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip()
    if not s:
        return s
    s = re.sub(r"(?:,\s*|\s+)\(?0\d{2,4}\)?(?:[\s\-–]?\d){5,}\s*$", "", s)
    s = re.sub(r"(?:,\s*|\s+)8-0\d{2,4}(?:-\d{2,}){2,5}\s*$", "", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        return ""

    out: list[str] = []
    seen_city: set[str] = set()
    has_real_city = False
    for p in parts:
        m = re.match(
            r"^(г\.|г/п|аг\.|д\.|дер\.|п\.|пос\.|поселок|городок)\s*(.+)$",
            p,
            flags=re.IGNORECASE,
        )
        if not m:
            out.append(p)
            continue
        loc = re.sub(r"\s+", " ", m.group(2)).strip()
        loc_norm = loc.casefold()
        if "не указано" in loc_norm:
            continue
        has_real_city = True
        if loc_norm in seen_city:
            continue
        seen_city.add(loc_norm)
        out.append(p)

    merged = ", ".join(out)
    if has_real_city:
        merged = re.sub(r"(?:,\s*|\s+)г\.\s*\(не\s*указано\)\b", "", merged, flags=re.IGNORECASE)
    merged = re.sub(r",\s*,", ",", merged)
    merged = re.sub(
        r"\b(г\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+)\s*,\s*\1\b",
        r"\1",
        merged,
        flags=re.IGNORECASE,
    )
    merged = re.sub(r"[,\s]+$", "", merged).strip()
    return merged


def _ensure_locality_in_address(address: str, *sources: str) -> str:
    """
    Гарантируем, что в адресе есть город/НП.
    В некоторых PDF город уходит в name-часть карточки, а в address остаётся только индекс/область/улица.
    Здесь вытаскиваем locality из исходных blob'ов и вставляем сразу после индекса.
    """
    compact = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip()
    if not compact:
        return compact
    compact = _normalize_bare_locality_after_postal(compact)
    compact = re.sub(r"\s+", " ", compact).strip()
    if _LOCALITY_RE.search(compact):
        return _dedupe_locality_in_address(compact)

    pool = " ".join((s or "").replace("\xa0", " ") for s in sources if s).strip()
    pool = re.sub(r"\s+", " ", pool)
    m = _LOCALITY_RE.search(pool)
    if not m:
        return _dedupe_locality_in_address(compact)
    locality = re.sub(r"[,\s]+$", "", m.group(1)).strip()
    if len(locality) < 3:
        return compact

    pm = re.search(r"\b(\d{6})\b", compact)
    if pm:
        postal = pm.group(1)
        injected = re.sub(
            r"^\s*" + re.escape(postal) + r"\s*,?\s*",
            f"{postal}, {locality}, ",
            compact,
            count=1,
            flags=re.IGNORECASE,
        )
        injected = re.sub(r",\s*,", ",", injected)
        return _dedupe_locality_in_address(re.sub(r"[,\s]+$", "", injected).strip())

    # Без индекса: просто добавим locality в начало.
    out = f"{locality}, {compact}"
    out = re.sub(r",\s*,", ",", out)
    return _dedupe_locality_in_address(re.sub(r"[,\s]+$", "", out).strip())


def repair_registry_address(address: str, owner_text: str, object_text: str) -> str:
    """
    Исправляет очевидно битые адреса после OCR/разрезания PDF, например:
    - "222310, г.8"
    - "222310, ..., г."
    Если в owner/object есть более информативный адресный хвост (ул./аг./д./...),
    подставляет его, сохраняя почтовый индекс.
    """
    compact = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip()
    if not compact:
        return compact
    compact = re.sub(r"([А-Яа-яA-Za-z])\.(\d)", r"\1. \2", compact)

    bad_city_num = bool(re.match(r"^\d{6},?\s*г\.\s*\d+\s*$", compact, flags=re.IGNORECASE))
    bad_truncated_city = bool(re.match(r"^\d{6},?.*[, ]г\.\s*$", compact, flags=re.IGNORECASE))
    if not bad_city_num and not bad_truncated_city:
        return compact

    pm = re.search(r"\b\d{6}\b", compact)
    if not pm:
        return compact
    postal = pm.group(0)
    hint = _extract_address_hint(owner_text) or _extract_address_hint(object_text)
    if not hint:
        return compact
    return f"{postal}, {hint}"


def extract_name_address_multiline(blob: str) -> tuple[str, str]:
    """
    Делит текст карточки (несколько строк) на наименование объекта/собственника и адрес для геокодера.
    Строка с «######, ул.» (или индекс с 12+ позиции) начинает адрес; дальнейшие строки с признаками
    адреса идут в адрес, остальные — обратно в наименование (типично для PDF БелНИЦ).
    """
    raw: list[str] = []
    for ln in blob.replace("\xa0", " ").splitlines():
        s = ln.strip()
        if not s:
            continue
        if _is_object_field_noise_line(s):
            continue
        raw.append(s)
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
            if _ADDRESS_HINT_LINE_RE.search(low) or POSTAL.search(line):
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


def _owner_blob_body_for_name_address(blob: str) -> str:
    """
    Убирает первую строку-метку «Собственник» (часто отдельной строкой в PDF),
    чтобы extract_name_address_multiline не обрывался на первой же итерации.
    """
    raw = [ln.strip() for ln in (blob or "").replace("\xa0", " ").splitlines() if ln.strip()]
    if not raw:
        return ""
    m = OWNER_START.match(raw[0])
    if not m:
        return (blob or "").strip()
    first_tail = (m.group(1) or "").strip()
    rest = raw[1:]
    if first_tail:
        return "\n".join([first_tail, *rest]).strip()
    return "\n".join(rest).strip()


def clean_owner_blob(blob: str) -> str:
    blob = blob.replace("\xa0", " ").strip()
    blob = _trim_tail_noise(blob)
    return re.sub(r"\s+", " ", blob).strip()


def _owner_names_from_naimenovanie_lines(blob: str) -> list[str]:
    """Строки вида «Наименование организации: …» из PDF-выгрузок."""
    found: list[str] = []
    for ln in (blob or "").replace("\xa0", " ").splitlines():
        s = re.sub(r"\s+", " ", ln).strip()
        m = re.match(
            r"(?i)(?:полное\s+)?наименование(?:\s+организации)?\s*[:;]\s*(.+)$",
            s,
        )
        if not m:
            continue
        val = m.group(1).strip(" ,;:\"'«»")
        if len(val) < 4 or re.search(r"^\d{6}\b", val):
            continue
        if re.search(r"\b(?:ул\.|улица|д\.|г\.)\b", val, flags=re.IGNORECASE):
            continue
        found.append(val)
    return found


def _select_canonical_owner_name(blob: str) -> str:
    """
    Выбирает каноничное имя собственника:
    приоритет — строки с юр-формой (ООО/ОАО/УП/...),
    без адресных и телефонных хвостов.
    """
    labelled = _owner_names_from_naimenovanie_lines(blob)
    labelled_set = set(labelled)
    lines: list[str] = list(labelled)
    for ln in (blob or "").replace("\xa0", " ").splitlines():
        s = re.sub(r"\s+", " ", ln).strip(" ,;")
        if not s:
            continue
        if re.match(r"(?i)(?:полное\s+)?наименование(?:\s+организации)?\s*[:;]", s):
            continue
        if _is_registry_noise_line(s):
            continue
        if s.casefold() in ("собственник", "объект"):
            continue
        if re.search(r"\b\d{6}\b", s):
            continue
        if re.search(r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\bтел\.?\b|\bфакс\b)", s, flags=re.IGNORECASE):
            continue
        if s in labelled_set:
            continue
        lines.append(s)
    if not lines:
        return ""

    legal = [s for s in lines if _OWNER_HINT_RE.search(s)]
    ranked = legal if legal else lines

    def _owner_line_score(s: str) -> int:
        score = 0
        if s in labelled_set:
            score += 28
        if _OWNER_HINT_RE.search(s):
            score += 80
        if _OWNER_ORG_HINT_RE.search(s):
            score += 38
        if re.search(r"[\"«»]", s):
            score += 8
        words = len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", s))
        score += min(24, words)
        score += min(12, len(s) // 12)
        # Штраф за явный служебный/нормативный хвост, который не должен быть частью owner.
        if re.search(
            r"\b(?:в\s+соответствии|об\s+охране\s+окружающей\s+среды|использует|принимает)\b",
            s,
            flags=re.IGNORECASE,
        ):
            score -= 45
        # Лёгкий штраф за "технические" хвосты в строке юрлица.
        if re.search(
            r"\b(?:по\s+проектированию|по\s+ремонту|по\s+строительству|площадка|участок)\b",
            s,
            flags=re.IGNORECASE,
        ):
            score -= 10
        # Слишком общий однословный фрагмент (например "Управление") почти всегда некорректен.
        if re.fullmatch(
            r"(?:управление|предприятие|организация|компания|филиал|участок|цех|отдел|дирекция|служба)",
            s.strip(),
            flags=re.IGNORECASE,
        ):
            score -= 65
        return score

    ranked.sort(key=lambda x: (-_owner_line_score(x), -len(x), x.casefold()))
    best = ranked[0]
    best_sc = _owner_line_score(best)
    if best_sc < 35:
        # Длинное наименование без явной ОПФ (трест, филиал, …) — не отбрасываем целиком.
        if len(best) >= 22 and best_sc >= 24 and re.search(r"[A-Za-zА-Яа-яЁё]{12,}", best):
            return best
        return ""
    return best


def _extract_owner_hint_from_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
    if not compact:
        return ""
    parts: list[str] = []
    for block in re.split(r"[\n\r]+", compact):
        block = re.sub(r"\s+", " ", block).strip(" ,;")
        if not block:
            continue
        if re.search(r"[;,]", block):
            parts.extend(p.strip() for p in re.split(r"[;,]", block) if p.strip())
        else:
            parts.append(block)
    best = ""
    best_score = -10_000
    for seg in parts:
        cand = seg
        postal = re.search(r"\b\d{6}\b", cand)
        if postal and postal.start() > 6:
            cand = cand[: postal.start()]
        elif postal:
            continue
        ph = re.search(r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\bтел\.?\b|\bфакс\b)", cand, re.IGNORECASE)
        if ph and ph.start() > 8:
            cand = cand[: ph.start()]
        elif ph:
            continue
        adr = re.search(r"\b(?:г\.|ул\.|улица|д\.|обл\.|область|район|р-н|аг\.|дер\.|пос\.)\b", cand, re.IGNORECASE)
        if adr and adr.start() > 10:
            cand = cand[: adr.start()]
        elif adr:
            continue
        cand = cand.strip(" ,;:.\"'«»")
        if not cand:
            continue
        if re.match(r"^\d{1,4}\s+", cand) and (_OWNER_HINT_RE.search(cand) or _OWNER_ORG_HINT_RE.search(cand)):
            cand = re.sub(r"^\d{1,4}\s+", "", cand).strip()
        if not cand:
            continue
        score = 0
        if _OWNER_HINT_RE.search(cand):
            score += 70
        if _OWNER_ORG_HINT_RE.search(cand):
            score += 40
        if re.search(r"[\"«»]", cand):
            score += 8
        score += min(22, len(cand) // 7)
        if len(cand) >= 14 and re.search(r"[A-Za-zА-Яа-яЁё]{10,}", cand) and not _OWNER_HINT_RE.search(cand):
            score += 18
        if re.fullmatch(
            r"(?:управление|предприятие|организация|компания|филиал|участок|цех|отдел|дирекция|служба)",
            cand.strip(),
            flags=re.IGNORECASE,
        ):
            score -= 60
        if score > best_score:
            best_score = score
            best = cand
    if best_score < 34:
        return ""
    return best


def _looks_like_owner_noise_value(text: str) -> bool:
    s = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
    if not s:
        return True
    if _is_registry_noise_line(s):
        return True
    if re.search(r"\b\d{6}\b", s):
        return True
    if re.search(r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\bтел\.?\b|\bфакс\b)", s, re.IGNORECASE):
        return True
    if re.search(r"\b(?:г\.|ул\.|улица|д\.|обл\.|область|район|р-н|аг\.|дер\.|пос\.)\b", s, re.IGNORECASE):
        return True
    return False


def owner_display_name(owner_blob: str, object_blob: str = "", address_text: str = "") -> str:
    canonical = _select_canonical_owner_name(owner_blob)
    if canonical:
        return canonical
    owner_body = _owner_blob_body_for_name_address(owner_blob)
    pool = f"{owner_blob} {object_blob} {address_text}"
    pool_body = f"{owner_body} {object_blob} {address_text}"
    hinted = _extract_owner_hint_from_text(pool)
    hinted_body = _extract_owner_hint_from_text(pool_body)
    if hinted_body and (not hinted or len(hinted_body) > len(hinted)):
        hinted = hinted_body
    if hinted:
        return hinted
    name, _addr = extract_name_address_multiline(owner_body)
    if len(name) >= 6 and not _looks_like_owner_noise_value(name):
        return name
    cleaned = clean_owner_blob(owner_body)
    if not _looks_like_owner_noise_value(cleaned):
        return cleaned
    return ""


def _phone_digits_reasonable(digits: str) -> bool:
    """Отсекаем слипшиеся «телефон + код объекта / хвост» (слишком длинная цепочка цифр)."""
    n = len(digits)
    if n < 5:
        return False
    if digits.startswith("375"):
        return n <= 12
    if digits.startswith(("80", "800")):
        return n <= 11
    # Национальный формат РБ без +375: обычно до 10 цифр; 11+ часто уже слипшийся мусор (56338191262).
    return n <= 10


def extract_phones_from_text(*blobs: str) -> str:
    """Выделяет телефоны/факс из сырого текста карточек объекта и собственника (реестр ecoinfo)."""
    text = "\n".join(b for b in blobs if b)
    if not text.strip():
        return ""
    text = _merge_split_phone_lines(text)
    # Ограничение длины групп и проверка _phone_digits_reasonable уменьшают слипание с кодами объектов.
    # Шаблон «ровно 11 цифр» убран — он часто цеплял лишние цифры из соседних полей.
    patterns = [
        r"(?<!\d)\(?0\d{2,4}\)?\s*[\d\s\-–]{5,18}(?:\s*,\s*[\d\s\-–]{3,12}){0,3}(?!\d)",
        r"8-\d{2,4}(?:-\d{2,}){2,5}(?!\d)",
        r"(?:тел\.?|факс)\s*[:\.]?\s*[\d\s\-–,\(\)]{5,22}(?=\s|$|[;А-Яа-яA-Za-zёЁ])",
        r"(?i)(?:тел(?:ефон)?\s*:|тел\s*\.?\s*:|ф\s*\.)\s*[\d\s\+()\-–]{6,26}(?=\s|$|[;А-Яа-яA-Za-zёЁ])",
        r"(?i)(?:моб\.?|сот\.?)\s*[:\.]?\s*(?:\+?\s*375\s*)?[\d\s\(\)\-–]{8,22}(?!\d)",
        r"(?<!\d)\+?\s*375\s*\(?\d{2,3}\)?\s*\d{2}[\s\-–]?\d{3}(?!\d)",
        r"(?<!\d)\+?\s*375\s*\(?\d{2,3}\)?\s*\d{3}[\s\-–]?\d{2}[\s\-–]?\d{2}(?!\d)",
        r"(?<!\d)\+?\s*375\s*\(?\d{2,3}\)?\s*\d{2,3}[\s\-–]?\d{2}[\s\-–]?\d{2,3}(?!\d)",
        # +375 с пробелами/скобками: «+375 (29) 563-38-19»
        r"(?<!\d)\+?\s*375(?:[\s\(\)\-–]*\d){9}(?!\d)",
        r"(?<!\d)(?:\+?375|80)\d{9}(?!\d)",
        r"(?<!\d)80\s*0\d{2}\s*\d{3}[\s\-–]?\d{2}[\s\-–]?\d{2}(?!\d)",
    ]
    seen_keys: set[str] = set()
    out: list[str] = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            s = re.sub(r"\s+", " ", m.group(0).strip()).rstrip(".,;")
            digits = re.sub(r"\D+", "", s)
            # «(029) 5633819 2 апреля» — жадный хвост цепляет одну цифру даты.
            s_trim = re.sub(r"\s\d$", "", s).strip()
            if s_trim != s:
                d_trim = re.sub(r"\D+", "", s_trim)
                if _phone_digits_reasonable(d_trim) and not _phone_digits_reasonable(digits):
                    s = s_trim
                    digits = d_trim
            if len(s) < 5:
                continue
            if not _phone_digits_reasonable(digits):
                continue
            if digits in seen_keys:
                continue
            seen_keys.add(digits)
            out.append(s)
            if len(out) >= 12:
                return "; ".join(out)
    # Fallback: если OCR слипает несколько номеров в одной строке с разделителями.
    for chunk in re.split(r"[,;/]|(?:\s{2,})", text):
        cand = re.sub(r"\s+", " ", chunk).strip(" ,;")
        if len(cand) < 6:
            continue
        if not re.search(r"\d{5,}", cand):
            continue
        if not re.search(r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\d{2,3}[\s\-]\d{2}[\s\-]\d{2})", cand):
            continue
        digits = re.sub(r"\D+", "", cand)
        if not _phone_digits_reasonable(digits):
            continue
        if digits in seen_keys:
            continue
        seen_keys.add(digits)
        out.append(cand)
        if len(out) >= 12:
            break
    return "; ".join(out)


_BALLOT_RE = re.compile(r"[\u2610\u2611\u2612]")


def infer_accepts_external_waste(object_blob: str) -> bool | None:
    """
    В PDF реестра ecoinfo у строки «Объект» справа две колонки-галочки:
    «Использует собственные», «Принимает от других». Вторая — признак приёма чужих отходов.

    В плоском тексте это часто две подряд «☐/☑» (U+2610/U+2611) в конце строки с телефоном.
    Нет явных галочек/фраз — None (неизвестно; для OCR/JPG без векторных галочек надёжность ниже).
    Поиск с координатами показывает только записи с явным True.
    """
    text = (object_blob or "").replace("\xa0", " ")
    if not text.strip():
        return None
    pair: tuple[str, str] | None = None
    for line in text.splitlines():
        boxes = _BALLOT_RE.findall(line)
        if len(boxes) == 2:
            pair = (boxes[0], boxes[1])
    if pair is None:
        for line in text.splitlines():
            boxes = _BALLOT_RE.findall(line)
            if len(boxes) >= 2:
                pair = (boxes[-2], boxes[-1])
                break
    if pair:
        _first, second = pair
        if second == "\u2610":
            return False
        if second in ("\u2611", "\u2612"):
            return True
    m = re.search(r"Принимает\s+от\s+других\s*([\u2610\u2611\u2612])", text, flags=re.IGNORECASE)
    if m:
        return m.group(1) != "\u2610"
    if re.search(r"не\s+принимает\s+(?:отходы?\s+)?от\s+других", text, flags=re.IGNORECASE):
        return False
    if re.search(r"принимает\s+отходы?\s+от\s+других", text, flags=re.IGNORECASE):
        return True
    return None


_ZWSP_RE = re.compile(r"[\ufeff\u200b\u200c\u200d\u2060]")
_PDF_NOISE_LINE_PATTERNS = (
    re.compile(r"^\s*$"),
    re.compile(r"^\s*Страница\s+\d+\s+из\s+\d+.*$", re.IGNORECASE),
    re.compile(r"^\s*\d{1,2}\s+[а-яё]+\s+\d{4}\s*г\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*\*+\s*$"),
    re.compile(r"^\s*(?:Использует\s+собственные|Принимает\s+от\s+других)\s*$", re.IGNORECASE),
    re.compile(r"^\s*Использует\s+собственные\s+Принимает\s+(?:от|он)\s+других\s*$", re.IGNORECASE),
)
_OCR_NORMALIZE_PATTERNS = (
    # Common legal-form OCR confusions.
    (re.compile(r"\b0ОО\b"), "ООО"),
    (re.compile(r"\bО0О\b"), "ООО"),
    (re.compile(r"\bОО0\b"), "ООО"),
    (re.compile(r"\bОА0\b"), "ОАО"),
    (re.compile(r"\b0А0\b"), "ОАО"),
    # Punctuation spacing around address tokens.
    (re.compile(r"\bг\s*[,;:]\s*"), "г. "),
    (re.compile(r"\bул\s*[,;:]\s*"), "ул. "),
    (re.compile(r"\bд\s*[,;:]\s*"), "д. "),
)


def _line_has_valuable_tokens(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if _fkko_line_parts(s):
        return True
    if OBJECT_START.search(s) or OWNER_START.search(s):
        return True
    if re.search(r"\b\d{6}\b", s):
        return True
    if re.search(r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\bтел\.?\b|\bфакс\b)", s, re.IGNORECASE):
        return True
    return False


def _drop_pdf_noise_lines(text: str) -> str:
    kept: list[str] = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if _line_has_valuable_tokens(s):
            kept.append(s)
            continue
        if any(p.match(s) for p in _PDF_NOISE_LINE_PATTERNS):
            continue
        kept.append(s)
    return "\n".join(kept)


def _normalize_ocr_artifacts(text: str) -> str:
    out = text or ""
    for pat, repl in _OCR_NORMALIZE_PATTERNS:
        out = pat.sub(repl, out)
    return out


def _preprocess_registry_pdf_plaintext(full_text: str) -> str:
    """
    После извлечения из PDF часто нет переносов: «…шапка 1111111 вид… Объект 1 … Собственник …».
    Парсер ждёт код ФККО в начале строки и отдельные строки карточки — вставляем \n в типичных местах.
    """
    full_text = _ZWSP_RE.sub("", full_text or "")
    full_text = full_text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    full_text = _normalize_ocr_artifacts(full_text)
    # «Объект» / «Object» и номер на разных строках (типичный вывод PDF).
    # Только короткий номер записи (≤5 цифр): иначе «Объект» + «220000, ул…» слипаются в ложный «Объект 220000».
    _obj_num_nl = re.compile(r"(?i)((?:Объект|[Oo]bject)\s*(?:№\.?))\s*\n\s*(\d{1,5})\b")
    _obj_nl = re.compile(r"(?i)(Объект|[Oo]bject)\s*\n\s*(\d{1,5})\b")
    while True:
        nxt = _obj_num_nl.sub(r"\1 \2", full_text)
        nxt = _obj_nl.sub(r"\1 \2", nxt)
        if nxt == full_text:
            break
        full_text = nxt
    # Код ФККО (7 цифр, без 8-й подряд) не в начале строки — новая строка.
    full_text = re.sub(r"(?<=[^\n\r\d])(\d{7})(?!\d)", r"\n\1", full_text)
    # Метки «Объект N» / «Собственник» внутри строки.
    full_text = re.sub(
        r"(?i)(?<!\n)\s+(?=(?:Объект|[Oo]bject)\s*(?:№\.?)?\s*\d+\b)",
        "\n",
        full_text,
    )
    full_text = re.sub(r"(?i)(?<!\n)\s+(?=Собственник\b)", "\n", full_text)
    full_text = _drop_pdf_noise_lines(full_text)
    return full_text


_FKKO_ANYWHERE = re.compile(r"(?<![0-9])([0-9]{7})(?![0-9])")
_OBJ_ANCHOR = re.compile(
    r"(?i)(?<![а-яёa-zA-Z0-9])(?:Объект|[Oo]bject)\s*(?:№\.?)?\s*(\d{1,5})\b",
)


def registry_repair_source_excerpt(
    full_text: str,
    object_id: int,
    waste_code: str | None,
    *,
    before: int = 3200,
    after: int = 9000,
    max_chars: int = 10_000,
) -> str:
    """
    Фрагмент нормализованного текста PDF вокруг карточки «Объект N» для LLM-repair.
    Используется, когда в распарсенной строке нет owner/phones — в candidates их не видно,
    а в исходнике они часто есть выше/рядом с меткой объекта.
    """
    if not full_text or not str(full_text).strip():
        return ""
    try:
        oid = int(object_id)
    except (TypeError, ValueError):
        return ""
    if oid <= 0:
        return ""

    wc7: str | None = None
    if waste_code:
        w = str(waste_code).strip()
        if len(w) == 7 and w.isdigit():
            wc7 = w

    anchored: list[int] = []
    loose: list[int] = []
    for m in _OBJ_ANCHOR.finditer(full_text):
        try:
            num = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if num != oid:
            continue
        pos = int(m.start())
        loose.append(pos)
        if wc7:
            fk = _last_fkko_span_before(full_text, pos)
            if fk is not None and fk[0] == wc7:
                anchored.append(pos)
        else:
            anchored.append(pos)

    positions = anchored if anchored else loose
    if not positions:
        return ""

    windows: list[tuple[int, int]] = []
    for pos in positions:
        s = max(0, pos - before)
        e = min(len(full_text), pos + after)
        windows.append((s, e))
    windows.sort(key=lambda item: item[0])
    merged: list[list[int]] = []
    for s, e in windows:
        if not merged or s > merged[-1][1] + 24:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    chunks = [full_text[s:e].strip() for s, e in merged]
    out = "\n…\n".join(x for x in chunks if x)
    if len(out) > max_chars:
        return out[:max_chars].rstrip() + "\n…[clipped]"
    return out


def _last_fkko_span_before(text: str, end_pos: int, horizon: int = 14_000) -> tuple[str, int, int] | None:
    """Последний 7-значный код ФККО в text[start:end_pos]. Возвращает (code, start, end) абсолютных позиций."""
    start = max(0, end_pos - horizon)
    chunk = text[start:end_pos]
    last_m: re.Match[str] | None = None
    for m in _FKKO_ANYWHERE.finditer(chunk):
        last_m = m
    if not last_m:
        return None
    code = last_m.group(1)
    abs_s = start + last_m.start()
    abs_e = start + last_m.end()
    return code, abs_s, abs_e


def _waste_type_between(text: str, code_abs_end: int, obj_line_start: int) -> str:
    snip = text[code_abs_end:obj_line_start].strip()
    snip = re.sub(r"\s+", " ", snip)
    return (snip[:900] or "—").strip()


def _extract_address_by_postal_lines(*blobs: str) -> str:
    """
    Fallback-адрес: берём строку с почтовым индексом и, при необходимости, склеиваем продолжение со следующей.
    Это помогает для выгрузок, где ул./г. идут на отдельной строке.
    """
    for blob in blobs:
        lines = [ln.strip() for ln in (blob or "").replace("\xa0", " ").splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if not re.search(r"\b\d{6}\b", ln):
                continue
            cand = ln
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                # Продолжение адреса часто без индекса и без служебных меток.
                if (
                    nxt
                    and not re.search(r"\b\d{6}\b", nxt)
                    and not OWNER_START.match(nxt)
                    and not OBJECT_START.match(nxt)
                    and not _PHONE_OR_FAX_RE.search(nxt)
                    and len(nxt) <= 140
                ):
                    cand = f"{cand}, {nxt}"
            cand = re.sub(r"\s+", " ", cand).strip(" ,;")
            if len(cand) >= 10:
                return cand
    return ""


def _score_address_candidate(address: str) -> int:
    s = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip()
    if not s:
        return -1000
    score = 0
    if re.search(r"\b\d{6}\b", s):
        score += 40
    if _LOCALITY_RE.search(s):
        score += 35
    if _DISTRICT_RE.search(s):
        score += 14
    if _REGION_RE.search(s):
        score += 14
    if re.search(r"\b(?:ул\.|улица|пер\.|просп\.|б-р|шоссе|д\.|дом|корп\.|к\.)\b", s, flags=re.IGNORECASE):
        score += 30
    if len(s) >= 18:
        score += min(20, len(s) // 15)
    if re.search(r"(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|\bтел\.?\b|\bфакс\b)", s, flags=re.IGNORECASE):
        score -= 30
    if "не указано" in s.casefold():
        score -= 25
    return score


def _pick_best_address_candidate(*candidates: str) -> str:
    scored = []
    for cand in candidates:
        c = re.sub(r"\s+", " ", (cand or "").replace("\xa0", " ")).strip(" ,;")
        if not c:
            continue
        scored.append((c, _score_address_candidate(c)))
    if not scored:
        return ""
    scored.sort(key=lambda item: (-item[1], -len(item[0]), item[0].casefold()))
    return scored[0][0]


def _best_address_line_from_blobs(*blobs: str) -> str:
    best = ""
    best_score = -10000
    for blob in blobs:
        for ln in (blob or "").replace("\xa0", " ").splitlines():
            s = re.sub(r"\s+", " ", ln).strip(" ,;")
            if len(s) < 8:
                continue
            score = _score_address_candidate(s)
            if score > best_score:
                best, best_score = s, score
    return best


def _normalize_address_for_scoring(address: str, *, owner_blob: str, object_blob: str) -> str:
    s = _trim_tail_noise(address)
    s = _ensure_locality_in_address(s, object_blob, owner_blob)
    s = repair_registry_address(s, owner_blob, object_blob)
    s = _dedupe_locality_in_address(s)
    s = _dedupe_consecutive_comma_segments(s)
    s = _canonicalize_address_from_components(s)
    s = _clean_address_noise_final(s)
    return s


def _select_best_canonical_address(
    primary: str,
    alternative: str,
    *,
    owner_blob: str,
    object_blob: str,
) -> tuple[str, str]:
    primary_norm = _normalize_address_for_scoring(primary, owner_blob=owner_blob, object_blob=object_blob)
    alt_norm = _normalize_address_for_scoring(alternative, owner_blob=owner_blob, object_blob=object_blob)
    p_score = _score_address_candidate(primary_norm)
    a_score = _score_address_candidate(alt_norm)
    if a_score > p_score:
        return alt_norm, f"address_selected_alternative(score:{a_score}>{p_score})"
    if p_score > a_score:
        return primary_norm, f"address_selected_primary(score:{p_score}>{a_score})"
    # Tie-breaker: prefer longer richer variant.
    if len(alt_norm) > len(primary_norm):
        return alt_norm, f"address_selected_alternative_by_length(len:{len(alt_norm)}>{len(primary_norm)})"
    return primary_norm, f"address_selected_primary_by_length(len:{len(primary_norm)}>={len(alt_norm)})"


def _score_owner_candidate(owner: str) -> int:
    s = re.sub(r"\s+", " ", (owner or "").replace("\xa0", " ")).strip()
    if not s:
        return -1000
    score = 10
    if not _looks_like_owner_noise_value(s):
        score += 55
    if re.search(r"\b(?:ООО|ОАО|ЧУП|ИП|УП|ЗАО|ПАО)\b", s, flags=re.IGNORECASE):
        score += 20
    if re.search(r"[\"«»]", s):
        score += 5
    if len(s) >= 12:
        score += min(15, len(s) // 8)
    return score


def _select_best_owner_candidate(primary: str, alternative: str) -> tuple[str, str]:
    p = re.sub(r"\s+", " ", (primary or "").replace("\xa0", " ")).strip(" ,;")
    a = re.sub(r"\s+", " ", (alternative or "").replace("\xa0", " ")).strip(" ,;")
    p = re.sub(r"[`´‘’“”]", '"', p)
    a = re.sub(r"[`´‘’“”]", '"', a)
    p = _normalize_phrase_dashes(p)
    a = _normalize_phrase_dashes(a)
    if p and a:
        p_low = p.casefold()
        a_low = a.casefold()
        if p_low in a_low and len(a) >= len(p) + 8:
            return a, "owner_selected_alternative_contains_primary"
        if a_low in p_low and len(p) >= len(a) + 8:
            return p, "owner_selected_primary_contains_alternative"
    p = _clean_owner_name_final(p)
    a = _clean_owner_name_final(a)
    p_score = _score_owner_candidate(p)
    a_score = _score_owner_candidate(a)
    if a_score > p_score:
        return a, f"owner_selected_alternative(score:{a_score}>{p_score})"
    if p_score > a_score:
        return p, f"owner_selected_primary(score:{p_score}>{a_score})"
    if len(a) > len(p):
        return a, f"owner_selected_alternative_by_length(len:{len(a)}>{len(p)})"
    return p, f"owner_selected_primary_by_length(len:{len(p)}>={len(a)})"


def _score_object_candidate(object_name: str) -> int:
    s = re.sub(r"\s+", " ", (object_name or "").replace("\xa0", " ")).strip()
    if not s or s in {"—", "-"}:
        return -1000
    score = 20
    if len(s) >= 8:
        score += min(35, len(s) // 3)
    if re.search(r"\b(?:установка|комплекс|площадка|полигон|линия|объект)\b", s, flags=re.IGNORECASE):
        score += 18
    if _is_registry_noise_line(s):
        score -= 35
    return score


def _select_best_object_candidate(primary: str, alternative: str) -> tuple[str, str]:
    p = re.sub(r"\s+", " ", (primary or "").replace("\xa0", " ")).strip(" ,;")
    a = re.sub(r"\s+", " ", (alternative or "").replace("\xa0", " ")).strip(" ,;")
    p_score = _score_object_candidate(p)
    a_score = _score_object_candidate(a)
    if a_score > p_score:
        return a, f"object_selected_alternative(score:{a_score}>{p_score})"
    if p_score > a_score:
        return p, f"object_selected_primary(score:{p_score}>{a_score})"
    if len(a) > len(p):
        return a, f"object_selected_alternative_by_length(len:{len(a)}>{len(p)})"
    return p, f"object_selected_primary_by_length(len:{len(p)}>={len(a)})"


def _score_phones_candidate(phones: str) -> int:
    s = re.sub(r"\s+", " ", (phones or "").replace("\xa0", " ")).strip()
    if not s:
        return -1000
    items = [p.strip() for p in s.split(";") if p.strip()]
    if not items:
        return -1000
    score = 10
    for item in items:
        digits = re.sub(r"\D+", "", item)
        if _phone_digits_reasonable(digits):
            score += 18
        else:
            score -= 10
    if len(items) <= 4:
        score += 8
    if len(s) > 120:
        score -= 10
    return score


def _select_best_phones_candidate(primary: str, alternative: str) -> tuple[str, str]:
    p = re.sub(r"\s+", " ", (primary or "").replace("\xa0", " ")).strip(" ,;")
    a = re.sub(r"\s+", " ", (alternative or "").replace("\xa0", " ")).strip(" ,;")
    p_score = _score_phones_candidate(p)
    a_score = _score_phones_candidate(a)
    if a_score > p_score:
        return a, f"phones_selected_alternative(score:{a_score}>{p_score})"
    if p_score > a_score:
        return p, f"phones_selected_primary(score:{p_score}>{a_score})"
    if len(a) > len(p):
        return a, f"phones_selected_alternative_by_length(len:{len(a)}>{len(p)})"
    return p, f"phones_selected_primary_by_length(len:{len(p)}>={len(a)})"


def _build_registry_record_row(
    reg_id: int,
    waste_code: str,
    waste_type_name: str,
    object_blob: str,
    owner_blob: str,
    source_part: int,
) -> dict[str, Any]:
    object_name, addr_obj = extract_name_address_multiline(object_blob)
    object_name = _clean_object_name_final(object_name, waste_type_name)
    canonical = _select_canonical_object_name(object_blob, waste_type_name)
    if canonical:
        can_hint = bool(_OBJECT_CANON_HINT_RE.search(canonical))
        obj_hint = bool(_OBJECT_CANON_HINT_RE.search(object_name))
        if (
            not object_name
            or (can_hint and not obj_hint)
            or (can_hint and canonical in object_name and len(object_name) >= len(canonical) + 18)
            or (can_hint and len(canonical) > len(object_name))
        ):
            object_name = canonical
    object_name = _clean_object_name_final(object_name, waste_type_name)
    _oname2, addr_own = extract_name_address_multiline(owner_blob)
    postal_fallback = _extract_address_by_postal_lines(object_blob, owner_blob)
    address = _pick_best_address_candidate(addr_obj, addr_own, postal_fallback, owner_blob)
    if len(address) < 8:
        address = _pick_best_address_candidate(postal_fallback, addr_obj, addr_own, owner_blob)
    address = _normalize_address_for_scoring(address, owner_blob=owner_blob, object_blob=object_blob)

    if not _LOCALITY_RE.search(address):
        pm = re.search(r"\b(\d{6})\b", address)
        if pm:
            postal = pm.group(1)
            address = re.sub(
                r"^\s*" + re.escape(postal) + r"\s*,?\s*",
                f"{postal}, г. (не указано), ",
                address.strip(),
                count=1,
                flags=re.IGNORECASE,
            )
            address = re.sub(r",\s*,", ",", address)
            address = re.sub(r"[,\s]+$", "", address).strip()
    address = _canonicalize_address_from_components(address)
    address = _clean_address_noise_final(address)
    owner_name = owner_display_name(owner_blob, object_blob, address)
    owner_name = _clean_owner_name_final(owner_name)

    # Частый OCR-кейс: адрес распознан только как индекс, а город прилип к object/owner.
    if re.fullmatch(r"\d{6}", address or ""):
        city_hint = (
            _extract_trailing_city_word(object_name)
            or _extract_trailing_city_word(owner_name)
            or _extract_trailing_city_word(object_blob)
            or _extract_trailing_city_word(owner_blob)
        )
        if city_hint:
            address = f"{address}, г. {city_hint}"
            object_name = _strip_trailing_city_word(object_name, city_hint)
            owner_name = _strip_trailing_city_word(owner_name, city_hint)

    phones = extract_phones_from_text(object_blob, owner_blob)
    row = {
        "id": reg_id,
        "owner": owner_name,
        "object_name": object_name or "—",
        "waste_code": waste_code,
        "waste_type_name": waste_type_name,
        "accepts_external_waste": infer_accepts_external_waste(object_blob),
        "address": address,
        "phones": phones,
        "source_part": source_part,
    }
    conf, notes = _compute_parse_confidence(
        row,
        raw_object_blob=object_blob,
        raw_owner_blob=owner_blob,
    )
    if conf < 60:
        repaired = _repair_low_confidence_row(
            dict(row),
            object_blob=object_blob,
            owner_blob=owner_blob,
            waste_type_name=waste_type_name,
        )
        r_conf, r_notes = _compute_parse_confidence(
            repaired,
            raw_object_blob=object_blob,
            raw_owner_blob=owner_blob,
        )
        if r_conf > conf:
            repair_notes = repaired.pop("__repair_notes", [])
            row = repaired
            conf, notes = r_conf, r_notes
            notes = [*notes, "repair_pass_applied"]
            if repair_notes:
                notes.extend([str(n) for n in repair_notes if n])
    row["parse_confidence"] = conf
    row["parse_notes"] = notes
    return row


def _repair_low_confidence_row(
    row: dict[str, Any],
    *,
    object_blob: str,
    owner_blob: str,
    waste_type_name: str,
) -> dict[str, Any]:
    out = dict(row)
    repair_notes: list[str] = []
    obj_blob = (object_blob or "").strip()
    own_blob = (owner_blob or "").strip()

    # Owner repair: prefer canonical or hint extraction from wider context.
    owner_now = str(out.get("owner") or "").strip()
    owner_alt = _select_canonical_owner_name(own_blob) or _extract_owner_hint_from_text(
        f"{own_blob} ; {obj_blob} ; {out.get('address') or ''}"
    )
    selected_owner, owner_note = _select_best_owner_candidate(owner_now, owner_alt or "")
    if selected_owner:
        out["owner"] = selected_owner
        repair_notes.append(owner_note)
    elif not str(out.get("owner") or "").strip():
        fb = clean_owner_blob(_owner_blob_body_for_name_address(own_blob))
        if (
            fb
            and len(fb) >= 10
            and (_OWNER_HINT_RE.search(fb) or _OWNER_ORG_HINT_RE.search(fb))
            and not _looks_like_owner_noise_value(fb)
        ):
            out["owner"] = re.sub(r"\s+", " ", fb)[:400]
            repair_notes.append("owner_repair_fallback_clean_blob")

    # Object repair: try stronger canonical selection from object blob.
    obj_now = str(out.get("object_name") or "").strip()
    obj_alt = _select_canonical_object_name(obj_blob, waste_type_name) or ""
    selected_obj, obj_note = _select_best_object_candidate(obj_now, obj_alt)
    if selected_obj:
        out["object_name"] = selected_obj
        repair_notes.append(obj_note)

    # Address repair: pick best candidate from all available signals and sanitize.
    addr_now = str(out.get("address") or "").strip()
    addr_alt = _pick_best_address_candidate(
        addr_now,
        _extract_address_by_postal_lines(obj_blob, own_blob),
        _best_address_line_from_blobs(obj_blob, own_blob),
        _extract_address_hint(obj_blob) or "",
        _extract_address_hint(own_blob) or "",
    )
    selected_addr, selected_note = _select_best_canonical_address(
        addr_now,
        addr_alt,
        owner_blob=own_blob,
        object_blob=obj_blob,
    )
    if selected_addr:
        out["address"] = selected_addr
        repair_notes.append(selected_note)

    # Phones repair: include address in fallback source for split lines.
    phones_now = str(out.get("phones") or "").strip()
    phones_alt = extract_phones_from_text(obj_blob, own_blob, str(out.get("address") or ""))
    selected_phones, phones_note = _select_best_phones_candidate(phones_now, phones_alt)
    if selected_phones:
        out["phones"] = selected_phones
        repair_notes.append(phones_note)

    if repair_notes:
        out["__repair_notes"] = repair_notes

    return out


def _compute_parse_confidence(
    row: dict[str, Any],
    *,
    raw_object_blob: str,
    raw_owner_blob: str,
) -> tuple[int, list[str]]:
    score = 100
    notes: list[str] = []

    waste_code = str(row.get("waste_code") or "").strip()
    if not re.fullmatch(r"\d{7}", waste_code):
        score -= 30
        notes.append("bad_waste_code")

    try:
        reg_id = int(row.get("id") or 0)
        if reg_id <= 0:
            raise ValueError
    except Exception:
        score -= 20
        notes.append("bad_object_id")

    object_name = str(row.get("object_name") or "").strip()
    if object_name in {"", "—", "-"}:
        score -= 20
        notes.append("object_placeholder")
    elif len(object_name) < 8:
        score -= 6
        notes.append("short_object_name")

    owner = str(row.get("owner") or "").strip()
    if not owner:
        score -= 20
        notes.append("owner_empty")
    elif _looks_like_owner_noise_value(owner):
        score -= 12
        notes.append("owner_looks_noisy")

    address = str(row.get("address") or "").strip()
    if not address:
        score -= 22
        notes.append("address_empty")
    else:
        if not re.search(r"\b\d{6}\b", address):
            score -= 6
            notes.append("address_no_postal")
        if not _LOCALITY_RE.search(address):
            score -= 10
            notes.append("address_no_locality")
        if _PHONE_OR_FAX_RE.search(address):
            score -= 8
            notes.append("address_contains_phone")

    phones = str(row.get("phones") or "").strip()
    if not phones:
        score -= 8
        notes.append("phones_empty")
    elif len(phones) > 120:
        score -= 5
        notes.append("phones_too_long")

    # If parser only got tiny blobs around anchors, confidence should be lower.
    if len((raw_object_blob or "").strip()) < 10:
        score -= 8
        notes.append("short_object_blob")
    if len((raw_owner_blob or "").strip()) < 4:
        score -= 4
        notes.append("short_owner_blob")

    score = max(0, min(100, int(score)))
    return score, notes


def _parse_object_owner_lines(lines: list[str]) -> tuple[str, str]:
    """Разбор тела карточки: первая строка содержит «Объект N» (возможен префикс до метки)."""
    if not lines:
        return "", ""
    first = lines[0].strip()
    mobj = re.search(r"(?i)(?:Объект|[Oo]bject)\s*(?:№\.?)?\s*(\d{1,5})\b", first)
    if not mobj:
        return "", ""
    tail = first[mobj.end() :].strip()
    owner_inline = ""
    inline_m = _INLINE_OWNER_SPLIT_RE.search(tail)
    if inline_m:
        owner_inline = tail[inline_m.end() :].strip()
        tail = tail[: inline_m.start()].strip()
    j = 1
    obj_chunks = [tail]
    while j < len(lines):
        stn = lines[j].strip()
        if OWNER_START.match(stn):
            break
        if OBJECT_START.match(stn) or _fkko_line_parts(stn):
            break
        obj_chunks.append(lines[j].strip())
        j += 1
    object_blob = "\n".join(x for x in obj_chunks if x).strip()
    owner_blob = ""
    if j >= len(lines):
        return object_blob, owner_blob
    found_owner = False
    while j < len(lines):
        stn = lines[j].strip()
        if not stn:
            j += 1
            continue
        if OWNER_START.match(stn):
            found_owner = True
            break
        if OBJECT_START.match(stn) or _fkko_line_parts(stn):
            break
        j += 1
    if found_owner and j < len(lines):
        owm = OWNER_START.match(lines[j].strip())
        if owm:
            own_tail = owm.group(1).strip()
            j += 1
            own_chunks = [own_tail]
            while j < len(lines):
                stn = lines[j].strip()
                if OBJECT_START.match(stn) or _fkko_line_parts(stn):
                    break
                own_chunks.append(stn)
                j += 1
            owner_blob = "\n".join(x for x in own_chunks if x).strip()
    if not owner_blob and owner_inline:
        owner_blob = owner_inline
    elif owner_blob and owner_inline:
        owner_blob = "\n".join(x for x in [owner_inline, owner_blob] if x).strip()
    return object_blob, owner_blob


def _parse_registry_anchor_fallback(text: str, source_part: int) -> list[dict[str, Any]]:
    """
    Если построчная сегментация не сработала (порядок строк PDF «ломаный»), ищем «Объект N»
    в тексте и код ФККО смотрим назад в окне.
    """
    matches = list(_OBJ_ANCHOR.finditer(text))
    if not matches:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    last_waste = ""
    last_type = "—"
    for i, m in enumerate(matches):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if i + 1 < len(matches):
            next_line_start = text.rfind("\n", 0, matches[i + 1].start()) + 1
            chunk = text[line_start:next_line_start]
        else:
            chunk = text[line_start:]
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue
        mobj = re.search(r"(?i)(?:Объект|[Oo]bject)\s*(?:№\.?)?\s*(\d{1,5})\b", lines[0])
        if not mobj:
            continue
        reg_id = int(mobj.group(1))
        fk = _last_fkko_span_before(text, line_start)
        if fk:
            last_waste, _cs, ce = fk
            last_type = _waste_type_between(text, ce, line_start)
        elif not last_waste:
            continue
        waste_code = last_waste
        waste_type_name = last_type
        object_blob, owner_blob = _parse_object_owner_lines(lines)
        if not object_blob and not owner_blob:
            continue
        key = (waste_code, reg_id, line_start)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            _build_registry_record_row(
                reg_id,
                waste_code,
                waste_type_name,
                object_blob,
                owner_blob,
                source_part,
            )
        )
    return out


def _is_registry_noise_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    if re.search(r"Страница\s+\d+\s+из\s+\d+", s, flags=re.IGNORECASE):
        return True
    if re.search(r"^\d{1,2}\s+[а-яё]+\s+\d{4}\s*г\.?$", s, flags=re.IGNORECASE):
        return True
    return False


_OWNER_HINT_RE = re.compile(
    r"\b(ООО|ОАО|ЗАО|УП|РУП|ЧУП|ОДО|ИП|КУП|ГУП|ГП|КПУП|КДУП|РУСП)\b",
    re.IGNORECASE,
)
_OWNER_ORG_HINT_RE = re.compile(
    r"(?:^|[^A-Za-zА-Яа-яЁё])(?:"
    r"филиал(?:а|ы|у|ом|е)?|управлени[ея]|трест(?:а|у|ом|е)?|комбинат(?:а|у|ом|е)?|завод(?:а|у|ом|е)?|"
    r"предприят\w*|организац\w*|компан\w*|дирекц\w*|объединени\w*|концерн\w*|холдинг\w*|служб\w*|"
    r"муниципал\w*|райпотреб\w*|потребсоюз\w*|кооператив\w*|ассоциац\w*|"
    r"учреждени\w*|акционерн\w*|унитарн\w*|государственн\w*"
    r")(?=$|[^A-Za-zА-Яа-яЁё])",
    re.IGNORECASE,
)


def _guess_owner_blob_from_lines(lines: list[str]) -> str:
    """
    Пытается извлечь собственника из потока строк записи (часто owner не помечен отдельным блоком).
    Берём первую строку с организационно-правовой формой + короткое продолжение.
    """
    if not lines:
        return ""
    for i, ln in enumerate(lines):
        s = (ln or "").strip()
        if not s:
            continue
        if not (_OWNER_HINT_RE.search(s) or _OWNER_ORG_HINT_RE.search(s)):
            continue
        parts = [s]
        j = i + 1
        while j < len(lines):
            nxt = (lines[j] or "").strip()
            if not nxt:
                break
            if _is_registry_noise_line(nxt):
                break
            if nxt.casefold() in ("собственник", "объект"):
                break
            if re.fullmatch(r"\d{3,6}", nxt) or re.fullmatch(r"\d{7}", nxt):
                break
            if re.search(r"\b\d{6}\b", nxt):
                break
            if _PHONE_OR_FAX_RE.search(nxt):
                break
            if len(" ".join(parts + [nxt])) > 280:
                break
            parts.append(nxt)
            j += 1
        return "\n".join(parts).strip()
    return ""


def _looks_like_fkko_anchor(lines: list[str], idx: int, stop_idx: int) -> bool:
    """
    Проверяет, что 7-значная строка действительно похожа на ФККО-код,
    а не на "хвост" телефона.
    """
    upper = min(stop_idx, idx + 6)
    for j in range(idx + 1, upper):
        s = (lines[j] or "").strip()
        if not s or _is_registry_noise_line(s):
            continue
        if s.casefold() in ("собственник", "объект"):
            continue
        if re.fullmatch(r"\d{1,7}", s):
            continue
        if re.search(r"\b\d{6}\b", s):
            return False
        if re.search(r"[A-Za-zА-Яа-яЁё]", s):
            return True
    return False


def _parse_registry_label_blocks(lines: list[str], source_part: int) -> list[dict[str, Any]]:
    """
    Fallback для выгрузок, где строки "Собственник"/"Объект" идут как отдельные метки колонок,
    а ID объекта вынесен в соседние строки (типично для части II).
    """
    clean = [ln.strip() for ln in lines if (ln or "").strip()]
    pair_starts: list[int] = []
    for i in range(len(clean) - 1):
        a = clean[i].casefold()
        b = clean[i + 1].casefold()
        if a == b:
            continue
        if {a, b} == {"собственник", "объект"}:
            pair_starts.append(i)
    if not pair_starts:
        return []

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for n, ps in enumerate(pair_starts):
        # ID часто расположен за 1-9 строк до пары меток "Собственник/Объект".
        reg_id: int | None = None
        id_line_idx = -1
        for k in range(ps - 1, max(-1, ps - 10), -1):
            cand = clean[k]
            if re.fullmatch(r"\d{3,6}", cand):
                try:
                    reg_id = int(cand)
                    id_line_idx = k
                    break
                except ValueError:
                    reg_id = None
        if reg_id is None:
            continue

        # Ищем ближайший 7-значный код ФККО вверх по тексту.
        fkko_line = -1
        waste_code = ""
        fallback_any_idx = -1
        fallback_any_code = ""
        for k in range(ps - 1, -1, -1):
            m = re.fullmatch(r"(\d{7})", clean[k])
            if m:
                if fallback_any_idx < 0:
                    fallback_any_idx = k
                    fallback_any_code = m.group(1)
                if _looks_like_fkko_anchor(clean, k, ps):
                    waste_code = m.group(1)
                    fkko_line = k
                    break
        if not waste_code and fallback_any_idx >= 0:
            waste_code = fallback_any_code
            fkko_line = fallback_any_idx
        if not waste_code:
            continue

        end = pair_starts[n + 1] if n + 1 < len(pair_starts) else len(clean)
        chunk = [ln for ln in clean[ps + 2 : end] if not _is_registry_noise_line(ln)]
        if not chunk:
            continue

        # В поточных выгрузках начало данных записи часто находится между ID и парой меток.
        pre_context: list[str] = []
        back_context: list[str] = []
        if id_line_idx >= 0:
            for ln in clean[id_line_idx + 1 : ps]:
                s = ln.strip()
                if not s or _is_registry_noise_line(s):
                    continue
                if s.casefold() in ("собственник", "объект"):
                    continue
                if re.fullmatch(r"\d{1,2}", s):
                    continue
                pre_context.append(s)
            # В части I важные поля (owner/phones) нередко расположены за несколько строк ДО ID.
            for ln in clean[max(0, id_line_idx - 10) : id_line_idx]:
                s = ln.strip()
                if not s or _is_registry_noise_line(s):
                    continue
                if s.casefold() in ("собственник", "объект"):
                    continue
                if re.fullmatch(r"\d{1,7}", s):
                    continue
                back_context.append(s)

        # Часто в хвост chunk уже попадает пролог следующей записи (ID + 1-4 строки до метки).
        # Обрезаем такой хвост, чтобы не склеивать соседние записи.
        cut_at = -1
        for idx, ln in enumerate(chunk):
            if re.fullmatch(r"\d{3,6}", ln):
                if len(chunk) - idx <= 5:
                    cut_at = idx
        if cut_at > 0:
            chunk = chunk[:cut_at]
        if not chunk and not pre_context:
            continue

        wname_parts = []
        if fkko_line >= 0:
            for ln in clean[fkko_line + 1 : ps]:
                if _is_registry_noise_line(ln):
                    continue
                if re.fullmatch(r"\d{3,6}", ln):
                    continue
                if re.fullmatch(r"\d{7}", ln):
                    break
                wname_parts.append(ln)
                if len(" ".join(wname_parts)) > 900:
                    break
        waste_type_name = re.sub(r"\s+", " ", " ".join(wname_parts)).strip() or "—"

        all_lines = (back_context + pre_context + chunk)[:180]
        object_blob = "\n".join(all_lines).strip()
        owner_blob = _guess_owner_blob_from_lines(all_lines)
        key = (waste_code, reg_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            _build_registry_record_row(
                reg_id,
                waste_code,
                waste_type_name,
                object_blob,
                owner_blob,
                source_part,
            )
        )
    return out


def preprocess_registry_plaintext(full_text: str) -> str:
    """
    Тяжёлая нормализация «сырого» текста PDF перед разбором.
    Вызывайте отдельно и передайте в iter_registry_plain_text(..., text_preprocessed=True),
    чтобы UI/джоб могли показать прогресс между извлечением страниц и разбором строк.
    """
    return _preprocess_registry_pdf_plaintext(full_text)


def iter_registry_plain_text(
    full_text: str,
    source_part: int,
    *,
    text_preprocessed: bool = False,
) -> Iterator[dict[str, Any]]:
    """
    Потоковый разбор текста реестра: отдаёт записи по мере готовности.
    Удобно для импорта больших файлов без накопления промежуточных структур в памяти.

    text_preprocessed: если True, full_text уже прошёл preprocess_registry_plaintext.
    """
    if not text_preprocessed:
        full_text = _preprocess_registry_pdf_plaintext(full_text)
    lines = full_text.splitlines()
    while lines and _fkko_line_parts(lines[0].strip()) is None:
        lines.pop(0)

    emitted = False

    # Pass 1: split by FKKO and extract structured segments.
    def _iter_structured_segments(seg: list[str]) -> Iterator[dict[str, Any]]:
        if not seg:
            return
        first = seg[0].strip()
        fkko = _fkko_line_parts(first)
        if not fkko:
            return
        waste_code, wtail = fkko[0], fkko[1]
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
                stn = remainder[j].strip()
                if OBJECT_START.match(stn) or _fkko_line_parts(stn) or OWNER_START.match(stn):
                    break
                obj_chunks.append(stn)
                j += 1
            object_blob = "\n".join(x for x in obj_chunks if x).strip()

            owner_blob = ""
            found_owner = False
            jj = j
            while jj < len(remainder):
                stn = remainder[jj].strip()
                if not stn:
                    jj += 1
                    continue
                if OWNER_START.match(stn):
                    found_owner = True
                    break
                if OBJECT_START.match(stn) or _fkko_line_parts(stn):
                    break
                jj += 1
            if found_owner and jj < len(remainder):
                owm = OWNER_START.match(remainder[jj].strip())
                if owm:
                    own_tail = owm.group(1).strip()
                    jj += 1
                    own_chunks = [own_tail]
                    while jj < len(remainder):
                        stn = remainder[jj].strip()
                        if OBJECT_START.match(stn) or _fkko_line_parts(stn):
                            break
                        own_chunks.append(stn)
                        jj += 1
                    owner_blob = "\n".join(x for x in own_chunks if x).strip()
                    j = jj

            yield {
                "reg_id": reg_id,
                "waste_code": waste_code,
                "waste_type_name": waste_type_name,
                "object_blob": object_blob,
                "owner_blob": owner_blob,
            }

    segments: list[dict[str, Any]] = []
    cur: list[str] = []
    for line in lines:
        st = line.strip()
        if _fkko_line_parts(st):
            if cur:
                segments.extend(_iter_structured_segments(cur))
            cur = [line]
            continue
        if cur:
            cur.append(line)
    if cur:
        segments.extend(_iter_structured_segments(cur))

    # Pass 2: extract fields from structured segments.
    for seg in segments:
        emitted = True
        yield _build_registry_record_row(
            int(seg["reg_id"]),
            str(seg["waste_code"]),
            str(seg["waste_type_name"]),
            str(seg["object_blob"]),
            str(seg["owner_blob"]),
            source_part,
        )
    if not emitted and len(full_text) > 12_000:
        fb = _parse_registry_anchor_fallback(full_text, source_part)
        if fb:
            yield from fb
            return
    if not emitted:
        fb2 = _parse_registry_label_blocks(lines, source_part)
        if fb2:
            yield from fb2


def parse_registry_plain_text(full_text: str, source_part: int) -> list[dict[str, Any]]:
    """
    Совместимость со старым API: возвращает список записей.
    """
    return list(iter_registry_plain_text(full_text, source_part, text_preprocessed=False))
