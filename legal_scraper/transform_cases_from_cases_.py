from pathlib import Path
import json
import sys
import types

# If psycopg2 isn't installed in this environment, provide a dummy module
# so we can import helper functions from load_property_rights_postgres without
# requiring a DB driver.
if "psycopg2" not in sys.modules:
    sys.modules["psycopg2"] = types.ModuleType("psycopg2")

from load_property_rights_postgres import (
    extract_sections,
    extract_text,
    extract_case_lines,
    extract_citation,
    extract_court,
    extract_date_from_text,
    extract_keywords,
    extract_judges,
    extract_case_summary,
    extract_winner_role,
    extract_procedural_history,
    extract_court_reasoning,
    extract_verdict_order,
    extract_plain_english_summary,
    extract_case_timeline,
    extract_case_arguments,
    extract_case_parties,
    normalize_whitespace,
)

SRC = Path("parsed_json_new/property_rights/cases")
TGT = Path("parsed_json_new/property_rights/cases")
TGT.mkdir(parents=True, exist_ok=True)

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_output(original: dict, filename: str) -> dict:
    doc_block = original.get("document") if isinstance(original.get("document"), dict) else {}
    base_original = (
        original.get("preserved_original_json")
        if isinstance(original.get("preserved_original_json"), dict)
        else original
    )
    title = normalize_whitespace(
        original.get("title")
        or doc_block.get("title")
        or base_original.get("title")
        or filename
    )
    source_file = (
        original.get("source_file")
        or doc_block.get("source_file")
        or base_original.get("source_file")
        or ""
    )
    sections = extract_sections(base_original)
    case_lines = extract_case_lines(sections)
    citation = extract_citation(sections)
    court = extract_court(sections)
    date_of_judgment = extract_date_from_text(title, sections)
    original_text = extract_text(base_original) or None
    keywords = extract_keywords(sections, f"{title} {original_text or ''}")
    judges = extract_judges(sections)
    dispute_summary = extract_case_summary(sections)
    if not dispute_summary and original_text:
        # fallback
        dispute_summary = " ".join(original_text.splitlines()[:3])[:400].strip() or None
    winner_role = extract_winner_role(original_text or "")
    procedural_history = extract_procedural_history(case_lines)
    court_reasoning = extract_court_reasoning(case_lines)
    verdict_order = extract_verdict_order(case_lines)
    if not winner_role and verdict_order:
        winner_role = extract_winner_role(verdict_order)

    plain_english_translation = extract_plain_english_summary(
        title, dispute_summary, verdict_order, winner_role
    )

    timeline = extract_case_timeline(case_lines)
    arguments = extract_case_arguments(case_lines)
    plaintiff, defendant = extract_case_parties(title)

    structured = {
        "case_metadata": {
            "citation": citation or "",
            "court": court or "",
            "date_of_judgment": str(date_of_judgment) if date_of_judgment else "",
            "jurisdiction": "",
            "dispute_summary": dispute_summary or "",
            "procedural_history": procedural_history or "",
            "court_reasoning": court_reasoning or "",
            "verdict_order": verdict_order or "",
            "plain_english_translation": plain_english_translation or "",
            "winner_role": winner_role or "",
            "original_text": original_text or "",
        },
        "case_judges": judges or [],
        "case_parties": [],
        "case_arguments": [],
        "case_timeline": [],
        "case_keywords": keywords or [],
        "case_related_acts": [],
        "case_related_sections": [],
        "reasoning": [],
        "important_facts": [],
        "citations": [],
        "verdicts": [],
    }

    if plaintiff:
        structured["case_parties"].append({"party_role": "plaintiff_appellant", "party_name": plaintiff})
    if defendant:
        structured["case_parties"].append({"party_role": "defendant_respondent", "party_name": defendant})

    for role, arg in arguments:
        structured["case_arguments"].append({"party_role": role, "argument": arg})

    for dt, text in timeline:
        structured["case_timeline"].append({"event_date": str(dt) if dt else "", "event_text": text})

    # citations from sections
    if citation:
        structured["citations"] = [citation]

    # decide if the file contains no useful data
    useful_fields = [citation, court, dispute_summary, judges, plaintiff, defendant, verdict_order, procedural_history, court_reasoning]
    has_useful = any(bool(f) for f in useful_fields)

    out = {
        "document": {
            "doc_key": Path(filename).stem,
            "document_type": "case",
            "title": title if has_useful else f"No relevant data for {Path(filename).stem}",
            "source_file": source_file,
        },
        "raw_text": original_text or "",
        "structured_data": structured,
        "preserved_original_json": base_original,
    }

    return out


def main():
    files = sorted(SRC.glob("*.json"))
    print(f"Found {len(files)} source case files")
    for p in files:
        try:
            original = load_json(p)
            out = build_output(original, p.name)
            tgt = TGT / p.name
            tgt.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            print("WROTE:", tgt)
        except Exception as e:
            print("FAILED:", p, e)


if __name__ == "__main__":
    main()
