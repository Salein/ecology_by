"""Нормализация текста после извлечения из PDF (реестр)."""

import app.services.user_registry_cache as urc
from app.services.user_registry_cache import (
    extract_pdf_text_from_bytes,
    normalize_registry_pdf_extracted_text,
    score_registry_pdf_plaintext_for_import,
)


def test_normalize_removes_soft_hyphen_and_zero_width():
    s = "ОО\u00adО «Тест»\u200b строка"
    out = normalize_registry_pdf_extracted_text(s)
    assert "\u00ad" not in out
    assert "\u200b" not in out
    assert "ООО" in out


def test_normalize_joins_hyphenated_line_break_between_letters():
    s = "Мобильная уста-\nновка для отходов"
    out = normalize_registry_pdf_extracted_text(s)
    assert "установка" in out
    assert "ста-\n" not in out


def test_normalize_does_not_join_digit_hyphen_line_break():
    s = "код 123-\n4567890 продолжение"
    out = normalize_registry_pdf_extracted_text(s)
    assert "123-\n4567890" in out or "123-4567890" in out
    # Не склеиваем цифры через перенос: с обеих сторон дефиса должны быть буквы.
    assert "1234567890" not in out.replace("\n", "")


def test_normalize_crlf_and_form_feed():
    s = "a\r\nb\x0cc"
    out = normalize_registry_pdf_extracted_text(s)
    assert "\r" not in out
    assert "a" in out and "b" in out and "c" in out


def test_score_prefers_fkko_and_object_markers():
    weak = "lorem ipsum " * 200
    strong = (
        "1111111 Вид отхода\nОбъект 1 Установка\n"
        "220000, г. Минск\nСобственник ООО Тест\n"
        "2222222 Другой\nОбъект 2 Площадка\nСобственник ИП Иванов\n"
    )
    assert score_registry_pdf_plaintext_for_import(weak) < score_registry_pdf_plaintext_for_import(strong)


def test_hybrid_extract_prefers_plumber_when_pymupdf_weak(monkeypatch):
    monkeypatch.setattr(urc.settings, "registry_pdf_text_backend", "hybrid")
    monkeypatch.setattr(urc.settings, "registry_pdf_hybrid_pymupdf_min_score", 500)

    def weak_pymupdf(_data: bytes, _page_progress=None) -> str:
        return normalize_registry_pdf_extracted_text("lorem ipsum " * 300)

    def strong_plumber(_data: bytes, _page_progress=None) -> str:
        return normalize_registry_pdf_extracted_text(
            "1111111 Вид отхода\nОбъект 1 Установка\n"
            "220000, г. Минск\nСобственник ООО Тест\n"
        )

    monkeypatch.setattr(urc, "_extract_pdf_text_pymupdf", weak_pymupdf)
    monkeypatch.setattr(urc, "_extract_pdf_text_pdfplumber", strong_plumber)

    out = extract_pdf_text_from_bytes(b"%PDF-1.4 fake", page_progress=None)
    assert "1111111" in out
    assert "Объект 1" in out
