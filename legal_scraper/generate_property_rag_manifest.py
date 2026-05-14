import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "parsed_json_new" / "property_rights"
OUTPUT_PATH = BASE_DIR / "metadata" / "property_rights_rag_manifest.json"

MAX_SUMMARY_CHARS = 650
MAX_RETRIEVAL_CHARS = 2400
MAX_HEADINGS = 20
MAX_KEYWORDS = 20

NOISE_LINES = {
    "source",
    "search",
    "main navigation",
    "mobile navigation",
    "legal document view",
    "document options",
    "translation",
}


def normalize_space(value: str) -> str:
    value = value.replace("â€”", "—").replace("â€“", "-")
    value = value.replace("â€œ", '"').replace("â€", '"').replace("â€™", "'")
    return re.sub(r"\s+", " ", value).strip()


def first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return normalize_space(value)
    return ""


def unique(values: Iterable[str], limit: Optional[int] = None) -> List[str]:
    seen = set()
    result = []
    for value in values:
        value = normalize_space(str(value)).strip(" ,.;")
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if limit and len(result) >= limit:
            break
    return result


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def document_info(payload: Dict[str, Any], path: Path) -> Dict[str, str]:
    document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
    preserved = (
        payload.get("preserved_original_json")
        if isinstance(payload.get("preserved_original_json"), dict)
        else {}
    )
    rel = path.relative_to(INPUT_DIR).as_posix()
    folder_type = rel.split("/", 1)[0].rstrip("s")
    if folder_type == "case":
        folder_type = "case"

    folder_doc_type = {
        "acts": "act",
        "articles": "article",
        "cases": "case",
        "sections": "section",
        "constitution": "act",
    }.get(rel.split("/", 1)[0], folder_type)

    doc_type = first_non_empty(
        document.get("document_type"),
        preserved.get("document_type"),
        folder_doc_type,
    )
    if doc_type in {"html", "pdf", "unknown"}:
        doc_type = folder_doc_type

    return {
        "doc_key": first_non_empty(document.get("doc_key"), path.stem),
        "document_type": doc_type,
        "title": first_non_empty(document.get("title"), preserved.get("title"), path.stem),
        "source_file": first_non_empty(document.get("source_file"), preserved.get("source_file")),
        "parsed_json_file": str(path.resolve()),
        "relative_path": rel,
    }


def preserved_sections(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    preserved = payload.get("preserved_original_json")
    if isinstance(preserved, dict):
        sections = preserved.get("sections")
        if isinstance(sections, list):
            return sections
    sections = payload.get("sections")
    return sections if isinstance(sections, list) else []


def preserved_pages(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    preserved = payload.get("preserved_original_json")
    if isinstance(preserved, dict):
        pages = preserved.get("extracted_pages")
        if isinstance(pages, list):
            return pages
    pages = payload.get("extracted_pages")
    return pages if isinstance(pages, list) else []


def section_headings(payload: Dict[str, Any]) -> List[str]:
    headings = []
    for section in preserved_sections(payload):
        heading = normalize_space(str(section.get("heading", "")))
        if heading and heading.lower() not in NOISE_LINES:
            headings.append(heading)
    if headings:
        return unique(headings, MAX_HEADINGS)

    page_text = " ".join(str(page.get("text", "")) for page in preserved_pages(payload))
    matches = re.findall(r"(?<![A-Za-z0-9])(\d{1,3}[A-Z]?\.\s+[^.]{3,90})", page_text)
    return unique(matches, MAX_HEADINGS)


def text_from_sections(payload: Dict[str, Any]) -> str:
    lines = []
    for section in preserved_sections(payload):
        heading = normalize_space(str(section.get("heading", "")))
        if heading and heading.lower() not in NOISE_LINES:
            lines.append(heading)
        for line in section.get("content") or []:
            line = normalize_space(str(line))
            if line:
                lines.append(line)
    return "\n".join(lines)


def canonical_text(payload: Dict[str, Any]) -> str:
    raw_text = first_non_empty(payload.get("raw_text"))
    structured = payload.get("structured_data") if isinstance(payload.get("structured_data"), dict) else {}
    case_meta = structured.get("case_metadata") if isinstance(structured.get("case_metadata"), dict) else {}
    case_text = first_non_empty(case_meta.get("original_text"))
    section_text = text_from_sections(payload)
    page_text = "\n".join(
        normalize_space(str(page.get("text", ""))) for page in preserved_pages(payload) if page.get("text")
    )
    if case_text and len(case_text) < 200 and (section_text or page_text):
        case_text = ""
    if raw_text and len(raw_text) < 200 and page_text:
        raw_text = ""
    return first_non_empty(case_text, section_text, page_text, raw_text)


def summarize_text(text: str, fallback_title: str) -> str:
    text = normalize_space(text)
    if not text:
        return fallback_title
    sentences = re.split(r"(?<=[.!?])\s+", text)
    picked = []
    for sentence in sentences:
        sentence = normalize_space(sentence)
        if len(sentence) < 25:
            continue
        picked.append(sentence)
        if len(" ".join(picked)) >= 360 or len(picked) >= 3:
            break
    summary = " ".join(picked) or text[:MAX_SUMMARY_CHARS]
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[: MAX_SUMMARY_CHARS - 3].rsplit(" ", 1)[0] + "..."
    return summary


def keywords_for(payload: Dict[str, Any], doc_type: str) -> List[str]:
    structured = payload.get("structured_data") if isinstance(payload.get("structured_data"), dict) else {}
    field_names = {
        "case": ["case_keywords"],
        "act": ["act_keywords"],
        "article": ["article_keywords"],
        "section": [],
    }.get(doc_type, [])

    values = []
    for field in field_names:
        for item in structured.get(field) or []:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                values.extend(v for v in item.values() if isinstance(v, str))

    if values:
        return unique(values, MAX_KEYWORDS)

    text = canonical_text(payload).lower()
    candidates = [
        "property",
        "registration",
        "sale deed",
        "mortgage",
        "lease",
        "possession",
        "mutation",
        "transfer",
        "inheritance",
        "partition",
        "compensation",
        "easement",
        "gift",
        "will",
        "injunction",
        "stamp duty",
        "land acquisition",
        "specific performance",
    ]
    return [candidate for candidate in candidates if candidate in text][:MAX_KEYWORDS]


def metadata_for(payload: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    structured = payload.get("structured_data") if isinstance(payload.get("structured_data"), dict) else {}
    if doc_type == "case":
        meta = structured.get("case_metadata") if isinstance(structured.get("case_metadata"), dict) else {}
        parties = structured.get("case_parties") if isinstance(structured.get("case_parties"), list) else []
        return {
            "court": first_non_empty(meta.get("court")),
            "citation": first_non_empty(meta.get("citation")),
            "date_of_judgment": first_non_empty(meta.get("date_of_judgment")),
            "winner_role": first_non_empty(meta.get("winner_role")),
            "parties": parties,
            "judges": structured.get("case_judges") or [],
            "verdict_order": first_non_empty(meta.get("verdict_order")),
        }
    if doc_type == "act":
        meta = structured.get("act_metadata") if isinstance(structured.get("act_metadata"), dict) else {}
        return {
            "act_number": first_non_empty(meta.get("act_number")),
            "enactment_date": first_non_empty(meta.get("enactment_date")),
            "status": first_non_empty(meta.get("status")),
            "section_count_hint": len(section_headings(payload)),
        }
    if doc_type == "article":
        meta = structured.get("article_metadata") if isinstance(structured.get("article_metadata"), dict) else {}
        return {
            "article_number": first_non_empty(meta.get("article_number")),
            "status": first_non_empty(meta.get("status")),
            "source_document": first_non_empty(meta.get("source_document"), "Constitution of India"),
        }
    return {}


def build_record(path: Path) -> Dict[str, Any]:
    payload = load_json(path)
    info = document_info(payload, path)
    text = canonical_text(payload)
    headings = section_headings(payload)
    metadata = metadata_for(payload, info["document_type"])
    summary = first_non_empty(
        metadata.get("verdict_order") if isinstance(metadata, dict) else "",
        summarize_text(text, info["title"]),
    )
    retrieval_parts = [
        info["title"],
        summary,
        " ".join(keywords_for(payload, info["document_type"])),
        " ".join(headings[:8]),
        text[:MAX_RETRIEVAL_CHARS],
    ]

    return {
        "id": info["doc_key"],
        "document_type": info["document_type"],
        "title": info["title"],
        "summary": summary,
        "keywords": keywords_for(payload, info["document_type"]),
        "metadata": metadata,
        "section_headings": headings,
        "locations": {
            "parsed_json_file": info["parsed_json_file"],
            "relative_path": info["relative_path"],
            "source_file": info["source_file"],
        },
        "rag": {
            "retrieval_text": normalize_space(" ".join(part for part in retrieval_parts if part))[
                :MAX_RETRIEVAL_CHARS
            ],
            "recommended_chunk_source": "source_file/raw_text for full chunking; manifest record for metadata filtering",
        },
        "stats": {
            "raw_text_chars": len(text),
            "section_heading_count": len(headings),
        },
    }


def main() -> None:
    records = [build_record(path) for path in sorted(INPUT_DIR.rglob("*.json"))]
    counts = Counter(record["document_type"] for record in records)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "property-rag-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(INPUT_DIR.resolve()),
        "document_count": len(records),
        "document_type_counts": dict(sorted(counts.items())),
        "description": (
            "Compact metadata manifest for property-rights RAG. Use records[*].rag.retrieval_text "
            "for quick embeddings or use locations/source files for larger chunking."
        ),
        "records": records,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} records to {OUTPUT_PATH}")
    print(dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
