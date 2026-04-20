"""Минимальные проверки парсера реестра (без PDF)."""

from app.services.registry_record_parser import (
    iter_registry_plain_text,
    _parse_registry_anchor_fallback,
    _preprocess_registry_pdf_plaintext,
    parse_registry_plain_text,
)

MINIMAL_REGISTRY = """
1111111 Тестовый вид отходов
Объект 1 Название объекта
220000, ул. Примерная, 1, г. Минск
Собственник ООО «Ромашка»
220000, ул. Примерная, 1, г. Минск
"""


def test_parse_minimal_segment():
    rows = parse_registry_plain_text(MINIMAL_REGISTRY, source_part=1)
    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert rows[0]["waste_code"] == "1111111"
    assert "Минск" in (rows[0].get("address") or "")


def test_iter_parser_matches_list_parser():
    rows_list = parse_registry_plain_text(MINIMAL_REGISTRY, source_part=1)
    rows_iter = list(iter_registry_plain_text(MINIMAL_REGISTRY, source_part=1))
    assert rows_iter == rows_list


def test_code_line_without_space_after_fkko():
    text = """
2222222Склейка без пробела после кода
Объект 2 Объект
220000, ул. А, 1, г. Минск
Собственник ООО Тест
220000, ул. А, 1, г. Минск
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0]["waste_code"] == "2222222"


def test_eight_digit_line_not_treated_as_fkko_block():
    """Строка из 8+ цифр подряд в начале не должна резаться как 7+остаток."""
    text = """
12345678 не код ФККО
1111111 Нормальный блок
Объект 3 X
220000, ул. Б, 2, г. Минск
Собственник Z
220000, ул. Б, 2, г. Минск
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0]["id"] == 3


def test_pdf_like_single_line_with_inline_object_and_owner():
    """Как из части PDF без переносов: шапка, код, вид, объект и собственник в одной строке."""
    text = (
        "Вводный текст реестра 1111111 Тестовый вид отходов Объект 1 Название объекта "
        "220000, ул. Примерная, 1, г. Минск Собственник ООО «Ромашка» "
        "220000, ул. Примерная, 1, г. Минск"
    )
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0]["waste_code"] == "1111111"
    assert rows[0]["id"] == 1
    assert "Минск" in (rows[0].get("address") or "")


def test_fkko_line_with_table_prefix_and_spaced_digits():
    """Как в PDF-таблице: мусор в начале строки и пробелы между цифрами кода."""
    text = """
| 3 1 1 1 1 1 1 Вид отходов
Объект 9 Название
220000, ул. В, 3, г. Минск
Собственник Юрлицо
220000, ул. В, 3, г. Минск
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0]["waste_code"] == "3111111"
    assert rows[0]["id"] == 9


def test_object_label_split_across_lines():
    text = """
5555555 Вид
Объект
4 Название объекта
220000, ул. Г, 4, г. Минск
Собственник X
220000, ул. Г, 4, г. Минск
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0]["waste_code"] == "5555555"
    assert rows[0]["id"] == 4


def test_anchor_fallback_when_code_not_at_line_start():
    """Построчный разбор не находит блок; якорь по «Объект» и код ФККО назад по тексту."""
    text = """
шапка реестра
 junk 6111111 название вида в середине строки хвост
ещё строка Объект 9 Название О
220000, ул. Якорная, 1, г. Минск
Собственник ООО Якорь
220000, ул. Якорная, 1, г. Минск
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0]["waste_code"] == "6111111"
    assert rows[0]["id"] == 9
    assert "Минск" in (rows[0].get("address") or "")


def test_anchor_fallback_finds_object_in_stream():
    t = _preprocess_registry_pdf_plaintext(
        "intro 7111111 waste Объект 2 A 220000, ул. Z, 1, г. Минск Собственник Q 220000, ул. Z, 1, г. Минск"
    )
    rows = _parse_registry_anchor_fallback(t, 1)
    assert len(rows) == 1
    assert rows[0]["waste_code"] == "7111111"
    assert rows[0]["id"] == 2


def test_part2_label_blocks_fallback():
    text = """
1110100
Вид отхода для части II
3390
220000, ул. Примерная, 7, г. Минск
Собственник
Объект
ООО Тестовый объект
220000, ул. Примерная, 7, г. Минск
80171234567
"""
    rows = parse_registry_plain_text(text, 2)
    assert len(rows) == 1
    assert rows[0]["source_part"] == 2
    assert rows[0]["waste_code"] == "1110100"
    assert rows[0]["id"] == 3390


def test_label_blocks_fallback_supports_object_then_owner_and_owner_guess():
    text = """
1110100
Вид отхода
1983
Дробильный ковш BF 70,2
ООО "Тестовая компания"
220020, ул. Тимирязева, 97-11, г. Минск
(029) 1894145
Объект
Собственник
220020, ул. Тимирязева, 97-11, г. Минск
(029) 1894145
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == 1983
    assert row["waste_code"] == "1110100"
    assert "ООО" in (row.get("owner") or "")
    assert "1894145" in (row.get("phones") or "")


def test_address_noise_cleanup_dedup_city_and_phone_tail():
    text = """
1111111 Вид
Объект 77 X
223034, г. Заславль, г. Заславль, г. (не указано), ул. Советская, 133, г. (0175) 443097
Собственник Y
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    addr = rows[0].get("address") or ""
    assert "г. Заславль, г. Заславль" not in addr
    assert "г. (не указано)" not in addr
    assert "(0175)" not in addr


def test_object_field_drops_service_noise_lines():
    text = """
1111111 Вид
Объект 91
объекты, которые принимают отходы от других
Мобильная установка
223034, г. Заславль, ул. Советская, 133
Собственник Y
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    obj = (rows[0].get("object_name") or "").casefold()
    assert "принимают отходы от других" not in obj
    assert "мобильная установка" in obj


def test_object_name_cleans_legal_tail_on_backend():
    text = """
1111111 Бой бетонных изделий
Объект 92 Стационарный дробильно-сортировочный комплекс Коммунальное унитарное предприятие по проектированию, ремонту и строительству дорог
223034, г. Заславль, ул. Советская, 133
Собственник Y
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("object_name") == "Стационарный дробильно-сортировочный комплекс"


def test_object_name_removes_waste_prefix_on_backend():
    text = """
1111111 Бой бетонных изделий
Объект 93 Бой бетонных изделий Дробильно-сортировочный комплекс
223034, г. Заславль, ул. Советская, 133
Собственник Y
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("object_name") == "Дробильно-сортировочный комплекс"


def test_object_name_prefers_equipment_like_line():
    text = """
1111111 Бой бетонных изделий
Объект 94
Площадка по обращению с отходами
Мобильная дробильно-сортировочная установка
223034, г. Заславль, ул. Советская, 133
Собственник Y
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("object_name") == "Мобильная дробильно-сортировочная установка"


def test_owner_name_prefers_legal_entity_line():
    text = """
1111111 Бой бетонных изделий
Объект 95 Мобильная установка
223034, г. Заславль, ул. Советская, 133
Собственник
Площадка переработки отходов
ООО "ЭкоРесурс"
223034, г. Заславль, ул. Советская, 133
(017) 123-45-67
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("owner") == 'ООО "ЭкоРесурс"'


def test_owner_name_skips_address_and_phone_noise():
    text = """
1111111 Бой бетонных изделий
Объект 96 Дробильно-сортировочный комплекс
223034, г. Заславль, ул. Советская, 133
Собственник
Коммунальное унитарное предприятие "ДорСтрой"
223034, г. Заславль, ул. Советская, 133
тел. +375 (29) 111-22-33
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("owner") == 'Коммунальное унитарное предприятие "ДорСтрой"'


def test_owner_name_prefers_clean_legal_line_over_service_tail():
    text = """
1111111 Бой бетонных изделий
Объект 97 Мобильная установка
223034, г. Заславль, ул. Советская, 133
Собственник
ООО "ЭкоРесурс"
ООО "ЭкоРесурс" в соответствии с законодательством об охране окружающей среды
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("owner") == 'ООО "ЭкоРесурс"'


def test_owner_name_avoids_generic_single_word_when_legal_line_exists():
    text = """
1111111 Бой бетонных изделий
Объект 99 Мобильная установка
223034, г. Заславль, ул. Советская, 133
Собственник
Управление
ОАО "ПМК-42"
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("owner") == 'ОАО "ПМК-42"'


def test_object_name_prefers_clean_equipment_line_over_service_tail():
    text = """
1111111 Бой бетонных изделий
Объект 98
Площадка по обращению с отходами
Мобильная дробильно-сортировочная установка
Мобильная дробильно-сортировочная установка в соответствии с законодательством об охране окружающей среды
223034, г. Заславль, ул. Советская, 133
Собственник Y
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("object_name") == "Мобильная дробильно-сортировочная установка"


def test_owner_name_uses_org_hint_when_legal_form_missing():
    text = """
1111111 Бой бетонных изделий
Объект 100 Мобильная установка
223034, г. Заславль, ул. Советская, 133
Собственник
дорожно-строительный трест Западный
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("owner") == "дорожно-строительный трест Западный"


def test_owner_name_supports_additional_legal_forms():
    text = """
1111111 Бой бетонных изделий
Объект 102 Мобильная установка
223034, г. Заславль, ул. Советская, 133
Собственник
КУП "Горремавтодор"
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0].get("owner") == 'КУП "Горремавтодор"'


def test_owner_name_fallback_from_object_blob_when_owner_empty():
    text = """
1111111 Бой бетонных изделий
Объект 101 филиал ОАО "Барановичский комбинат ЖБК"
223034, г. Заславль, ул. Советская, 133
Собственник
223034, г. Заславль, ул. Советская, 133
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    owner = rows[0].get("owner") or ""
    assert "ОАО" in owner
    assert "комбинат ЖБК" in owner
