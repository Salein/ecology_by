"""Минимальные проверки парсера реестра (без PDF)."""

from app.services.registry_record_parser import (
    _select_best_canonical_address,
    _select_best_object_candidate,
    _select_best_owner_candidate,
    _select_best_phones_candidate,
    extract_phones_from_text,
    infer_accepts_external_waste,
    iter_registry_plain_text,
    owner_display_name,
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
    assert rows[0].get("accepts_external_waste") is None


def test_infer_accepts_external_waste_unknown_without_markers():
    assert infer_accepts_external_waste("") is None
    assert infer_accepts_external_waste("   ") is None
    assert infer_accepts_external_waste("ООО Овощ без галочек") is None


def test_infer_accepts_external_waste_ballot_second_column():
    assert infer_accepts_external_waste("тел. ☑ ☐") is False
    assert infer_accepts_external_waste("тел. ☑ ☑") is True


def test_infer_accepts_external_waste_phrases():
    assert infer_accepts_external_waste("не принимает от других") is False
    assert infer_accepts_external_waste("принимает отходы от других") is True


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


def test_owner_display_name_after_standalone_sobstvennik_line():
    name = owner_display_name("Собственник\nООО «Мира»", "", "")
    assert "ООО" in name
    assert "Мира" in name


def test_extract_phones_mob_label():
    t = "моб. +375 (29) 555-66-77 офис"
    phones = extract_phones_from_text(t)
    assert "375" in phones
    assert "555" in phones or "66-77" in phones


def test_extract_phones_merge_plus375_split_across_lines():
    t = "+375 (29)\n563-38-19"
    phones = extract_phones_from_text(t)
    assert "375" in phones
    assert "563" in phones


def test_extract_phones_telefon_colon_without_dot():
    t = "тел: +375 (29) 555-66-77 справки"
    phones = extract_phones_from_text(t)
    assert "375" in phones


def test_bare_city_after_postal_gets_g_prefix_in_ensure_locality():
    from app.services.registry_record_parser import _ensure_locality_in_address

    addr = _ensure_locality_in_address(
        "220030, \u041c\u0438\u043d\u0441\u043a, \u0443\u043b. \u041f\u043e\u0431\u0435\u0434\u044b, \u0434. 1",
        "",
        "",
    )
    assert "\u0433." in addr
    assert "\u041c\u0438\u043d\u0441\u043a" in addr


def test_owner_canonical_from_naimenovanie_line():
    from app.services.registry_record_parser import _select_canonical_owner_name

    blob = """Собственник
Наименование организации: ООО «Ромашка плюс»
"""
    assert "Ромашка" in (_select_canonical_owner_name(blob) or "")


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


def test_preprocess_drops_header_noise_lines():
    text = """
Страница 14 из 1999
22 апреля 2026 г.
1111111 Вид отхода
Объект 103 Установка
220000, ул. Примерная, 1, г. Минск
Собственник ООО "Тест"
220000, ул. Примерная, 1, г. Минск
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0]["id"] == 103
    assert rows[0]["waste_code"] == "1111111"


def test_ocr_table_header_noise_line_with_prinimaet_on_drugih_is_ignored():
    text = """
Реестр объектов
Использует собственные Принимает он других
1110100 Зачистки от производства твердых сыров
Объект 3245Коммунальное производственное унитарное предприятие
224008, ул. Ковельская, д.1, г. Брест 8 (0162) 59 39 54
Собственник Коммунальное производственное унитарное предприятие
224008, ул. Ковельская, д.1, г. Брест (0162) 59 39 55
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    row = rows[0]
    assert row["waste_code"] == "1110100"
    assert row["id"] == 3245
    assert "Ковельская" in (row.get("address") or "")


def test_ocr_brest_sample_owner_object_address_cleanup():
    text = """
1110100 Зачистки от производства твердых сыров
Объект 3245 Коммунальное производственное — унитарное предприятие "Брестский мусороперерабатывающий завод"
224008, г. Брест, г. Брест, ул. Ковельская, д. 1 (0162) 59 39 55
Собственник унитарное предприятие "Брестский мусороперерабатывающий завод"
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    row = rows[0]
    owner = row.get("owner") or ""
    obj = row.get("object_name") or ""
    addr = row.get("address") or ""
    assert "унитарное предприятие" in owner.casefold()
    assert "коммунальное производственное" in obj.casefold() or "мусороперерабатывающий" in obj.casefold()
    assert "г. Брест, г. Брест" not in addr
    assert "Ковельская" in addr


def test_owner_and_object_do_not_keep_address_or_phone_tail():
    text = """
1110400 Остатки пряностей
Объект 1199 Котел Kalvis 950 (котельная Осиповичского ГУ) г. Осиповичи, ул. Калинина +375 (225) 23-962
Собственник ОАО "Бобруйский КХП" г. Бобруйск, Могилевская обл. +375 (225) 68-964
213824, г. Осиповичи, ул. Калинина
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    row = rows[0]
    obj = (row.get("object_name") or "").casefold()
    owner = (row.get("owner") or "").casefold()
    assert "ул." not in obj
    assert "г. осиповичи" not in obj
    assert "ул." not in owner
    assert "г. бобруйск" not in owner


def test_extract_phones_keeps_multiple_numbers_from_same_line():
    t = '+375 (225) 23-962, +375 (225) 68-964'
    phones = extract_phones_from_text(t)
    assert "23-962" in phones or "23962" in phones
    assert "68-964" in phones or "68964" in phones


def test_postal_only_address_moves_city_from_object_tail():
    text = """
1110500 Отходы зерновые
Объект 3176 Цех гранулирования растительного сырья Бобруйск
Собственник ООО "Экогран Пром Плюс" Бобруйск
213824
"""
    rows = parse_registry_plain_text(text, 2)
    assert len(rows) == 1
    row = rows[0]
    assert row.get("address") == "213824, г. Бобруйск"
    assert not (row.get("object_name") or "").casefold().endswith("бобруйск")


def test_address_candidate_prefers_structured_address():
    text = """
1111111 Вид
Объект 104 Комплекс
минская область
220020, г. Минск, ул. Тимирязева, 97-11
Собственник ООО "ЭкоРесурс"
220020, г. Минск, ул. Тимирязева, 97-11
тел. +375 (29) 111-22-33
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    addr = rows[0].get("address") or ""
    assert "220020" in addr
    assert "Тимирязева" in addr


def test_object_line_with_inline_owner_split():
    text = """
1111111 Вид
Объект 105 Мобильная установка Собственник ООО "ЭкоТест"
220020, г. Минск, ул. Тимирязева, 97-11
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    assert rows[0]["id"] == 105
    assert "Мобильная установка" in (rows[0].get("object_name") or "")
    assert "ООО" in (rows[0].get("owner") or "")


def test_owner_guess_supports_org_hint_without_legal_form():
    text = """
1111111 Вид
Объект 106 Дробильно-сортировочная установка
220020, г. Минск, ул. Тимирязева, 97-11
Собственник
дорожно-строительный трест Центральный
220020, г. Минск, ул. Тимирязева, 97-11
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    owner = rows[0].get("owner") or ""
    assert "трест" in owner.casefold()


def test_parse_confidence_present_and_high_for_clean_row():
    text = """
1111111 Вид
Объект 107 Мобильная дробильно-сортировочная установка
220020, г. Минск, ул. Тимирязева, 97-11
Собственник ООО "ЭкоРесурс"
220020, г. Минск, ул. Тимирязева, 97-11
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.get("parse_confidence"), int)
    assert row["parse_confidence"] >= 70
    assert isinstance(row.get("parse_notes"), list)


def test_ocr_normalization_restores_legal_form():
    text = """
1111111 Вид
Объект 108 Установка
220020, г, Минск, ул, Тимирязева, 97-11
Собственник 0ОО "ЭкоРесурс"
220020, г, Минск, ул, Тимирязева, 97-11
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    owner = rows[0].get("owner") or ""
    assert "ООО" in owner
    addr = rows[0].get("address") or ""
    assert "г." in addr
    assert "ул." in addr


def test_repair_pass_improves_confidence_for_sparse_owner_line():
    text = """
1111111 Вид
Объект 109 Мобильная установка
220020, г. Минск, ул. Тимирязева, 97-11
Собственник
дорожно-строительный трест Западный
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    row = rows[0]
    assert row.get("parse_confidence", 0) >= 60
    notes = row.get("parse_notes") or []
    assert isinstance(notes, list)


def test_two_pass_parsing_multiple_objects_in_one_fkko_segment():
    text = """
1111111 Вид отхода
Объект 201 Установка А
220000, г. Минск, ул. А, 1
Собственник ООО "Альфа"
220000, г. Минск, ул. А, 1
Объект 202 Установка Б
220001, г. Минск, ул. Б, 2
Собственник ООО "Бета"
220001, г. Минск, ул. Б, 2
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 2
    ids = sorted(int(r["id"]) for r in rows)
    assert ids == [201, 202]


def test_address_component_canonicalization_keeps_core_fields():
    text = """
1111111 Вид
Объект 301 Комплекс
220020, г. Минск, ул. Тимирязева, д. 97-11, корпус 2
Собственник ООО "ЭкоРесурс"
220020, г. Минск, ул. Тимирязева, д. 97-11
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    addr = rows[0].get("address") or ""
    assert "220020" in addr
    assert "г. Минск" in addr
    assert "ул. Тимирязева" in addr
    assert "д. 97-11" in addr


def test_address_component_canonicalization_keeps_region_and_district():
    text = """
1111111 Вид
Объект 302 Комплекс
220020, г. Минск, Минский р-н, Минская обл., ул. Тимирязева, д. 97-11
Собственник ООО "ЭкоРесурс"
220020, г. Минск, Минский р-н, Минская обл., ул. Тимирязева, д. 97-11
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    addr = rows[0].get("address") or ""
    assert "Минский р-н" in addr
    assert "Минская обл." in addr


def test_low_conf_repair_uses_best_address_line_from_blobs():
    text = """
1111111 Вид
Объект 303 Комплекс
Минская обл.
Собственник ООО "Тест"
220020, г. Минск, ул. Тимирязева, д. 97-11
"""
    rows = parse_registry_plain_text(text, 1)
    assert len(rows) == 1
    addr = rows[0].get("address") or ""
    assert "220020" in addr
    assert "Тимирязева" in addr


def test_select_best_canonical_address_prefers_alternative_by_score():
    primary = "Минская обл."
    alternative = "220020, г. Минск, Минская обл., ул. Тимирязева, д. 97-11"
    chosen, note = _select_best_canonical_address(
        primary,
        alternative,
        owner_blob="Собственник ООО Тест",
        object_blob="Объект 1",
    )
    assert "220020" in chosen
    assert "г. Минск" in chosen
    assert note.startswith("address_selected_alternative")


def test_select_best_owner_candidate_prefers_alternative():
    chosen, note = _select_best_owner_candidate(
        "г. Минск, ул. Тестовая, 1",
        'ООО "ЭкоРесурс"',
    )
    assert "ООО" in chosen
    assert note.startswith("owner_selected_alternative")


def test_select_best_object_candidate_prefers_informative_name():
    chosen, note = _select_best_object_candidate(
        "—",
        "Мобильная дробильно-сортировочная установка",
    )
    assert "установка" in chosen.lower()
    assert note.startswith("object_selected_alternative")


def test_select_best_phones_candidate_prefers_valid_numbers():
    chosen, note = _select_best_phones_candidate(
        "",
        "+375 (29) 563-38-19; (017) 123-45-67",
    )
    assert "375" in chosen
    assert note.startswith("phones_selected_alternative")
