from pathlib import Path

import pdfplumber


def extract_pdf_text_to_file(pdf_path: Path, out_txt: Path) -> tuple[int, int]:
    """Потоково пишет текст страниц в файл; возвращает (число страниц, символов)."""
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    chars = 0
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        with open(out_txt, "w", encoding="utf-8") as f:
            for page in pdf.pages:
                t = page.extract_text() or ""
                f.write(t)
                f.write("\n\n")
                chars += len(t)
    return n, chars
