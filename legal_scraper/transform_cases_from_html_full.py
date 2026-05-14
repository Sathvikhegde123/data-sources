import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from parser import parse_html_file
from load_property_rights_postgres import (
    extract_case_lines,
    extract_case_parties,
    extract_citation,
    extract_court,
    extract_date_from_text,
    extract_keywords,
    extract_judges,
    extract_text,
    extract_winner_role,
    is_argument_line,
    is_reasoning_line,
    is_verdict_line,
    normalize_whitespace,
    parse_date_from_text,
    strip_page_markers,
)

BASE_DIR = Path(__file__).resolve().parent
RAW_HTML_DIR = BASE_DIR / "raw_html" / "property_rights"
EXISTING_CASES_DIR = BASE_DIR / "parsed_json_new" / "property_rights" / "cases"
OUTPUT_DIR = BASE_DIR / "parsed_json_new" / "property_rights" / "new_cases"


def iter_case_stems() -> List[str]:
    if not EXISTING_CASES_DIR.exists():
        raise FileNotFoundError(f"Missing cases folder: {EXISTING_CASES_DIR}")
    stems = sorted({path.stem for path in EXISTING_CASES_DIR.glob("*.json")})
    return stems


def join_case_lines_full(lines: Iterable[str]) -> Optional[str]:
    cleaned = [strip_page_markers(line) for line in lines if strip_page_markers(line)]
    if not cleaned:
        return None
    return " ".join(cleaned)


def extract_case_summary_full(lines: List[str]) -> Optional[str]:
    if not lines:
        return None
    summary = " ".join(lines[:2])
    return summary.strip() or None


def extract_procedural_history_full(lines: List[str]) -> Optional[str]:
    selected: List[str] = []
    for line in lines[:45]:
        lowered = line.lower()
        if is_reasoning_line(line) or is_verdict_line(line):
            continue
        if (
            re.match(r"^\d+[\).]\s+", line)
            or any(
                marker in lowered
                for marker in (
                    "filed",
                    "suit",
                    "appeal",
                    "petition",
                    "plaintiff",
                    "defendant",
                    "appellant",
                    "respondent",
                    "trial court",
                    "high court",
                )
            )
        ):
            selected.append(line)
        if len(selected) >= 8:
            break
    return join_case_lines_full(selected)


def extract_court_reasoning_full(lines: List[str]) -> Optional[str]:
    reasoning = [line for line in lines if is_reasoning_line(line) and not is_verdict_line(line)]
    if len(reasoning) < 3:
        middle_start = max(0, len(lines) // 2 - 4)
        middle_end = min(len(lines), middle_start + 12)
        fallback = [
            line
            for line in lines[middle_start:middle_end]
            if not is_argument_line(line) and not is_verdict_line(line)
        ]
        reasoning.extend(fallback)
    return join_case_lines_full(reasoning[:8])


def extract_verdict_order_full(lines: List[str]) -> Optional[str]:
    verdicts = [line for line in lines if is_verdict_line(line)]
    if verdicts:
        return join_case_lines_full(verdicts[-4:])
    tail = [line for line in lines[-8:] if line]
    return join_case_lines_full(tail[-3:])


def extract_plain_english_summary_full(
    title: str,
    dispute_summary: Optional[str],
    verdict_order: Optional[str],
    winner_role: Optional[str],
) -> Optional[str]:
    parts: List[str] = []
    if dispute_summary:
        parts.append(f"This case is about: {dispute_summary}")
    else:
        parties = title.rsplit(" on ", 1)[0]
        parts.append(f"This case concerns the dispute in {parties}.")
    if verdict_order:
        parts.append(f"Final order: {verdict_order}")
    if winner_role == "plaintiff_appellant":
        parts.append("The final outcome appears to favour the plaintiff/appellant side.")
    elif winner_role == "defendant_respondent":
        parts.append("The final outcome appears to favour the defendant/respondent side.")
    elif winner_role == "mixed":
        parts.append("The final outcome appears mixed or partly allowed.")
    return join_case_lines_full(parts)


def extract_case_timeline_full(lines: List[str]) -> List[Tuple[Optional[str], str]]:
    events: List[Tuple[Optional[str], str]] = []
    seen = set()
    for line in lines:
        event_date = parse_date_from_text(line)
        if not event_date:
            continue
        event = strip_page_markers(line)
        if not event or event in seen:
            continue
        seen.add(event)
        events.append((str(event_date), event))
        if len(events) >= 12:
            break
    return events


def extract_case_arguments_full(lines: List[str]) -> List[Tuple[str, str]]:
    arguments: List[Tuple[str, str]] = []
    for line in lines:
        if not is_argument_line(line):
            continue
        lowered = line.lower()
        if any(role in lowered for role in ("defendant", "respondent", "revenue")):
            party_role = "defendant_respondent"
        else:
            party_role = "plaintiff_appellant"
        arguments.append((party_role, strip_page_markers(line)))
        if len(arguments) >= 12:
            break
    return arguments


def build_output(original: Dict[str, Any], filename: str, source_html: Path) -> Dict[str, Any]:
    title = normalize_whitespace(original.get("title") or filename)
    case_lines = extract_case_lines(original.get("sections") or [])
    citation = extract_citation(original.get("sections") or [])
    court = extract_court(original.get("sections") or [])
    date_of_judgment = extract_date_from_text(title, original.get("sections") or [])
    original_text = extract_text(original) or ""
    keywords = extract_keywords(original.get("sections") or [], f"{title} {original_text}")
    judges = extract_judges(original.get("sections") or [])

    dispute_summary = extract_case_summary_full(case_lines)
    winner_role = extract_winner_role(original_text or "")
    procedural_history = extract_procedural_history_full(case_lines)
    court_reasoning = extract_court_reasoning_full(case_lines)
    verdict_order = extract_verdict_order_full(case_lines)
    if not winner_role and verdict_order:
        winner_role = extract_winner_role(verdict_order)

    plain_english_translation = extract_plain_english_summary_full(
        title, dispute_summary, verdict_order, winner_role
    )

    timeline = extract_case_timeline_full(case_lines)
    arguments = extract_case_arguments_full(case_lines)
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
        structured["case_parties"].append(
            {"party_role": "plaintiff_appellant", "party_name": plaintiff}
        )
    if defendant:
        structured["case_parties"].append(
            {"party_role": "defendant_respondent", "party_name": defendant}
        )

    for role, arg in arguments:
        structured["case_arguments"].append({"party_role": role, "argument": arg})

    for dt, text in timeline:
        structured["case_timeline"].append({"event_date": dt or "", "event_text": text})

    if citation:
        structured["citations"] = [citation]

    out = {
        "document": {
            "doc_key": Path(filename).stem,
            "document_type": "case",
            "title": title,
            "source_file": original.get("source_file", str(source_html)),
        },
        "raw_text": original_text,
        "structured_data": structured,
        "preserved_original_json": original,
    }

    return out


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stems = iter_case_stems()
    print(f"Found {len(stems)} case names to match")

    matched = 0
    missing = 0
    for stem in stems:
        html_path = RAW_HTML_DIR / f"{stem}.html"
        if not html_path.exists():
            missing += 1
            print(f"MISSING HTML: {html_path}")
            continue

        original = parse_html_file(html_path)
        out = build_output(original, f"{stem}.json", html_path)
        out_path = OUTPUT_DIR / f"{stem}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        matched += 1

    print(f"WROTE {matched} files to {OUTPUT_DIR}")
    if missing:
        print(f"Missing HTML files: {missing}")


if __name__ == "__main__":
    main()
