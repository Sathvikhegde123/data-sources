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
EXTERNAL_PDF_DIRS = [
    BASE_DIR.parent / "property-acts-and-laws",
]


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


def parse_akoma_ntoso(soup: BeautifulSoup, path: Path) -> Dict | None:
    container = soup.select_one(".akoma-ntoso")
    if not container:
        return None

    title_node = container.select_one(".doc_title")
    title = clean_text(title_node.get_text(" ", strip=True)) if title_node else path.stem

    sections: List[Dict] = []
    source_node = container.select_one(".docsource_main")
    if source_node:
        source_text = clean_text(source_node.get_text(" ", strip=True))
        if source_text:
            sections.append(
                {
                    "heading": "source",
                    "level": 1,
                    "content": [source_text],
                }
            )

    for section in container.select("section.akn-section"):
        heading_node = section.select_one(":scope > h3")
        heading = clean_text(heading_node.get_text(" ", strip=True)) if heading_node else "section"
        content: List[str] = []

        for para in section.select(".akn-p"):
            para_text = clean_text(para.get_text(" ", strip=True))
            if para_text:
                content.append(para_text)

        # Fallback for cases where text is inside akn-content without akn-p wrappers
        if not content:
            for node in section.select(".akn-content"):
                node_text = clean_text(node.get_text(" ", strip=True))
                if node_text:
                    content.append(node_text)

        if content:
            sections.append(
                {
                    "heading": heading,
                    "level": 2,
                    "content": content,
                }
            )

    links = []
    for a in container.find_all("a", href=True):
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


def parse_html_file(path: Path) -> Dict:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    akn_parsed = parse_akoma_ntoso(soup, path)
    if akn_parsed is not None:
        return akn_parsed

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


def format_pdf_title(stem: str) -> str:
    parts = stem.replace("_", " ").split()
    if not parts:
        return stem
    return " ".join(part.capitalize() for part in parts)


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


def parse_external_pdfs(max_pages: int) -> int:
    count = 0
    for source_dir in EXTERNAL_PDF_DIRS:
        if not source_dir.exists():
            continue
        for pdf_file in source_dir.rglob("*.pdf"):
            output_path = PARSED_DIR / "property_rights" / "acts" / f"{pdf_file.stem}.json"
            try:
                parsed = parse_pdf_file(pdf_file, max_pages=max_pages)
                parsed["title"] = format_pdf_title(pdf_file.stem)
                write_json(parsed, output_path)
                count += 1
                logging.info("Parsed external PDF -> %s", output_path)
            except Exception as exc:
                logging.exception("Failed parsing external PDF %s: %s", pdf_file, exc)

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse scraped HTML and PDFs into JSON.")
    parser.add_argument("--max-pdf-pages", type=int, default=20)
    args = parser.parse_args()

    setup_logging()

    html_count = parse_all_html()
    pdf_count = parse_all_pdfs(max_pages=args.max_pdf_pages)
    external_pdf_count = parse_external_pdfs(max_pages=args.max_pdf_pages)

    logging.info(
        "Finished parsing. HTML files: %s | PDF files: %s | External PDFs: %s",
        html_count,
        pdf_count,
        external_pdf_count,
    )


if __name__ == "__main__":
    main()
