import os
import json
import re
from pathlib import Path
from typing import Dict, Any

# =========================================================
# CONFIG
# =========================================================

INPUT_DIR = Path("parsed_json/property_rights")
OUTPUT_DIR = Path("parsed_json_new/property_rights")

# =========================================================
# REQUIRED OUTPUT SCHEMA (minimal defaults)
# =========================================================

REQUIRED_SCHEMA = {
    "document": {
        "doc_key": "",
        "document_type": "",
        "title": "",
        "source_file": ""
    },

    "raw_text": "",

    "structured_data": {
        "article_metadata": {},
        "article_amendments": [],
        "article_related_cases": [],
        "article_keywords": [],

        "act_metadata": {},
        "act_sections": [],
        "act_keywords": [],

        "section_metadata": {},

        "case_metadata": {
            "citation": "",
            "court": "",
            "date_of_judgment": "",
            "jurisdiction": "",
            "dispute_summary": "",
            "procedural_history": "",
            "court_reasoning": "",
            "verdict_order": "",
            "plain_english_translation": "",
            "winner_role": "",
            "original_text": ""
        },
        "case_judges": [],
        "case_parties": [],
        "case_arguments": [],
        "case_timeline": [],
        "case_keywords": [],
        "case_related_acts": [],
        "case_related_sections": [],

        "reasoning": [],
        "important_facts": [],
        "citations": [],
        "verdicts": []
    },

    "preserved_original_json": {}
}


def detect_document_type(path_str: str) -> str:
    path_lower = path_str.lower()

    if "case" in path_lower:
        return "case"

    if "act" in path_lower:
        return "act"

    if "section" in path_lower:
        return "section"

    if "article" in path_lower:
        return "article"

    return "unknown"


def extract_raw_text(original: Dict[str, Any]) -> str:
    parts = []

    # include title
    title = original.get("title")
    if title:
        parts.append(title)

    for sec in original.get("sections", []):
        heading = sec.get("heading") or ""
        if heading:
            parts.append(heading)

        for c in sec.get("content", []):
            if isinstance(c, str) and c.strip():
                parts.append(c.strip())

    # fall back to any top-level text fields
    for key in ["text", "body", "content"]:
        if original.get(key):
            if isinstance(original[key], str):
                parts.append(original[key])

    return "\n\n".join(parts).strip()


def find_section_by_heading(original: Dict[str, Any], needle: str):
    needle_lower = needle.lower()
    for sec in original.get("sections", []):
        heading = (sec.get("heading") or "").lower()
        if needle_lower in heading:
            return sec
    return None


def extract_date_from_title(title: str) -> str:
    if not title:
        return ""

    # patterns like 'on 27 March, 1992' or 'on 27 March 1992' or '27 March, 1992'
    m = re.search(r"(\d{1,2}\s+\w+\s*,?\s*\d{4})", title)
    if m:
        return m.group(1)

    # patterns like '1992' fallback
    m2 = re.search(r"\b(19|20)\d{2}\b", title)
    if m2:
        return m2.group(0)

    return ""


def extract_citations(original: Dict[str, Any]):
    citations = []
    for link in original.get("links", []):
        href = link.get("href") or ""
        text = link.get("text") or ""
        if "/doc/" in href or text:
            citations.append(text or href)
    return citations


def transform(original: Dict[str, Any], source_path: str) -> Dict[str, Any]:
    out = json.loads(json.dumps(REQUIRED_SCHEMA))  # deep copy defaults

    name = Path(source_path).stem

    out["document"]["doc_key"] = name
    out["document"]["document_type"] = detect_document_type(source_path)
    out["document"]["title"] = original.get("title", "")
    out["document"]["source_file"] = original.get("source_file", source_path)

    raw_text = extract_raw_text(original)
    out["raw_text"] = raw_text

    # case metadata
    cm = out["structured_data"]["case_metadata"]
    # citation
    eq = find_section_by_heading(original, "equivalent citations")
    if eq:
        cm["citation"] = "\n\n".join(eq.get("content", []))[:1000]
    else:
        cm["citation"] = original.get("title", "")

    # court
    court = None
    for sec in original.get("sections", []):
        h = sec.get("heading") or ""
        if "high court" in h.lower() or "supreme court" in h.lower() or "court" in h.lower():
            court = h
            break
    cm["court"] = court or ""

    cm["date_of_judgment"] = extract_date_from_title(original.get("title", ""))

    # put raw_text into original_text
    cm["original_text"] = raw_text[:100000]

    # keywords - try Top AI Tags or Related user Queries
    tags_sec = find_section_by_heading(original, "Top AI Tags") or find_section_by_heading(original, "Related user Queries")
    if tags_sec:
        keywords = []
        for it in tags_sec.get("content", []):
            if isinstance(it, str) and it.strip():
                # split CSV-like lists
                for part in re.split(r"[,;\n]", it):
                    p = part.strip()
                    if p:
                        keywords.append(p)
        out["structured_data"]["case_keywords"] = keywords

    out["structured_data"]["citations"] = extract_citations(original)

    out["preserved_original_json"] = original

    return out


def process_all():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_files = list(INPUT_DIR.rglob("*.json"))

    print(f"FOUND {len(json_files)} files to transform")

    for p in json_files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)

            transformed = transform(data, str(p))

            rel_path = p.relative_to(INPUT_DIR)
            out_path = OUTPUT_DIR / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(transformed, f, ensure_ascii=False, indent=2)

            print(f"WROTE -> {out_path}")

        except Exception as e:
            print(f"FAILED {p}: {e}")


if __name__ == "__main__":
    process_all()