from app.services.pdf_extract import extract_pdf_bytes


def extract_text_from_upload(data: bytes) -> dict:
    return extract_pdf_bytes(data)


__all__ = ["extract_pdf_bytes", "extract_text_from_upload"]
