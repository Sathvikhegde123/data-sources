import argparse
import json
import logging
import re
from pathlib import Path
from typing import Dict, List

from bs4 import BeautifulSoup
from pypdf import PdfReader


BASE_DIR = Path(__file__).resolve().parent
RAW_HTML_DIR = BASE_DIR / "raw_html"
RAW_PDF_DIR = BASE_DIR / "raw_pdfs"
PARSED_DIR = BASE_DIR / "parsed_json"
PARSER_LOG = BASE_DIR / "logs" / "parser.log"


def setup_logging() -> None:
    PARSER_LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(PARSER_LOG, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_html_file(path: Path) -> Dict:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    title = clean_text(soup.title.text) if soup.title and soup.title.text else path.stem

    sections: List[Dict] = []
    current_section = {
        "heading": "preamble",
        "level": 0,
        "content": [],
    }

    for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        text = clean_text(node.get_text(" ", strip=True))
        if not text:
            continue

        if re.fullmatch(r"h[1-6]", node.name or ""):
            if current_section["content"] or current_section["heading"] != "preamble":
                sections.append(current_section)
            current_section = {
                "heading": text,
                "level": int(node.name[1]),
                "content": [],
            }
        else:
            current_section["content"].append(text)

    if current_section["content"] or current_section["heading"] != "preamble":
        sections.append(current_section)

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        anchor_text = clean_text(a.get_text(" ", strip=True))
        if href:
            links.append({"href": href, "text": anchor_text})

    return {
        "source_file": str(path),
        "document_type": "html",
        "title": title,
        "sections": sections,
        "links": links,
    }


def parse_pdf_file(path: Path, max_pages: int = 20) -> Dict:
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages[:max_pages], start=1):
        text = page.extract_text() or ""
        text = clean_text(text)
        pages.append({"page_number": i, "text": text})

    return {
        "source_file": str(path),
        "document_type": "pdf",
        "title": path.stem,
        "page_count": len(reader.pages),
        "extracted_pages": pages,
    }


def write_json(payload: Dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_all_html() -> int:
    count = 0
    for html_file in RAW_HTML_DIR.rglob("*.html"):
        relative = html_file.relative_to(RAW_HTML_DIR)
        output_path = (PARSED_DIR / relative).with_suffix(".json")

        try:
            parsed = parse_html_file(html_file)
            write_json(parsed, output_path)
            count += 1
            logging.info("Parsed HTML -> %s", output_path)
        except Exception as exc:
            logging.exception("Failed parsing HTML %s: %s", html_file, exc)

    return count


def parse_all_pdfs(max_pages: int) -> int:
    count = 0
    for pdf_file in RAW_PDF_DIR.rglob("*.pdf"):
        relative = pdf_file.relative_to(RAW_PDF_DIR)
        output_path = (PARSED_DIR / relative).with_suffix(".json")

        try:
            parsed = parse_pdf_file(pdf_file, max_pages=max_pages)
            write_json(parsed, output_path)
            count += 1
            logging.info("Parsed PDF -> %s", output_path)
        except Exception as exc:
            logging.exception("Failed parsing PDF %s: %s", pdf_file, exc)

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse scraped HTML and PDFs into JSON.")
    parser.add_argument("--max-pdf-pages", type=int, default=20)
    args = parser.parse_args()

    setup_logging()

    html_count = parse_all_html()
    pdf_count = parse_all_pdfs(max_pages=args.max_pdf_pages)

    logging.info("Finished parsing. HTML files: %s | PDF files: %s", html_count, pdf_count)


if __name__ == "__main__":
    main()
