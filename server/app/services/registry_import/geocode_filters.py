"""Фильтрация адресов перед геокодированием (Nominatim)."""
from __future__ import annotations

import re

_POSTAL_RE = re.compile(r"\b\d{6}\b")
_ADDR_HINT_RE = re.compile(
    r"\b(г\.|г/п|аг\.|д\.|дер\.|п\.|пос\.|поселок|городок|ул\.|улица|пер\.|просп\.|б-р|шоссе)\b",
    re.IGNORECASE,
)


def _is_address_geocode_candidate(addr: str) -> bool:
    """
    Быстрый фильтр адресов перед Nominatim:
    - отсеивает заведомо пустые/служебные строки;
    - пропускает только строки с признаками адреса (индекс/маркеры населённого пункта или улицы).
    """
    a = " ".join((addr or "").replace("\xa0", " ").split()).strip()
    if len(a) < 8:
        return False
    low = a.casefold()
    if low in {"—", "-", "не указан", "не указано", "адрес отсутствует"}:
        return False
    if "не указано" in low and not _POSTAL_RE.search(a):
        return False
    if _POSTAL_RE.search(a):
        return True
    return bool(_ADDR_HINT_RE.search(a))


def _normalize_addr_key(s: str) -> str:
    s = " ".join((s or "").replace("\xa0", " ").split()).casefold()
    return s[:280]
