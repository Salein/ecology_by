from pathlib import Path

import pdfplumber


def extract_pdf(path: Path) -> dict:
    text_parts: list[str] = []
    tables_preview: list[list[list[str | None]]] = []
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t)
            if i < 3:
                for table in (page.extract_tables() or [])[:2]:
                    if table:
                        tables_preview.append(table)
    return {
        "pages": n,
        "text": "\n\n".join(text_parts).strip(),
        "tables_preview": tables_preview[:5],
    }


def _extract_fitz(data: bytes) -> dict:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        parts: list[str] = []
        for page in doc:
            t = page.get_text()
            if t and t.strip():
                parts.append(t)
        return {
            "pages": doc.page_count,
            "text": "\n\n".join(parts).strip(),
            "tables_preview": [],
        }
    finally:
        doc.close()


def extract_pdf_bytes(data: bytes) -> dict:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            return extract_pdf(Path(tmp.name))
        except Exception:
            return _extract_fitz(data)
