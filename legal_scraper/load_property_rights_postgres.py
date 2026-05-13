import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg2

BASE_DIR = Path(__file__).resolve().parent
PROPERTY_RIGHTS_DIR = BASE_DIR / "parsed_json" / "property_rights"
SCHEMA_PATH = BASE_DIR / "db" / "schema_property_rights.sql"
ENV_PATH = BASE_DIR / ".env"

SKIP_HEADINGS = {
    "source",
    "indian kanoon - search engine for indian law",
    "search",
    "main navigation",
    "mobile navigation",
    "legal document view",
    "tools for analyzing structure and cite text of judgments",
    "unlock advanced research with prism ai",
    "document options",
    "related ai tags, queries and research notes",
    "translation",
    "top ai tags",
    "related user queries",
}

KEYWORD_HEADINGS = {"top ai tags", "related user queries"}

KEYWORD_BLOCKLIST = {
    "judgment",
    "judgments",
    "case law",
    "legal research",
    "indian kanoon",
    "document",
    "court",
    "supreme court",
    "high court",
    "law",
    "laws",
}

LEGAL_KEYWORD_WHITELIST = {
    "act",
    "adverse",
    "agreement",
    "appeal",
    "article",
    "attorney",
    "conveyance",
    "deed",
    "easement",
    "estate",
    "evidence",
    "gift",
    "injunction",
    "lease",
    "limitation",
    "mortgage",
    "mutation",
    "partition",
    "possession",
    "property",
    "registration",
    "relief",
    "sale",
    "section",
    "specific",
    "stamp",
    "succession",
    "suit",
    "tenant",
    "title",
    "transfer",
    "will",
}

WEAK_LEGAL_KEYWORDS = {"act", "article", "section"}

NOISE_TEXT = {
    "login required",
    "you need to be signed in to use the ai legal assistant for this judgment.",
    "ask questions about the document",
    "get legal explanations and summaries",
    "save your chat history",
    "new user? sign up here",
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_dsn() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "postgres")
    password = os.environ.get("PGPASSWORD", "")
    database = os.environ.get("PGDATABASE", "property_rights")

    parts = [
        f"host={host}",
        f"port={port}",
        f"user={user}",
        f"dbname={database}",
    ]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


def ensure_schema(conn) -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()


def iter_json_files() -> Iterable[Path]:
    if not PROPERTY_RIGHTS_DIR.exists():
        raise FileNotFoundError(f"Property rights folder not found: {PROPERTY_RIGHTS_DIR}")
    return sorted(PROPERTY_RIGHTS_DIR.rglob("*.json"))


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def unique_preserve(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        value = normalize_whitespace(value)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def detect_document_type(rel_path: Path, title: str) -> str:
    parts = rel_path.parts
    if parts:
        root = parts[0].lower()
        if root in {"articles", "acts", "cases", "sections", "constitution"}:
            mapping = {
                "articles": "article",
                "acts": "act",
                "cases": "case",
                "sections": "section",
                "constitution": "act",
            }
            return mapping[root]

    title_lower = title.lower()
    if " vs " in title_lower or " v. " in title_lower or " v " in title_lower:
        return "case"
    if title_lower.startswith("section "):
        return "section"
    if "article" in title_lower:
        return "article"
    if "constitution" in title_lower:
        return "act"
    if "act" in title_lower:
        return "act"
    return "unknown"


def extract_sections(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return payload.get("sections") or []


def extract_pages(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return payload.get("extracted_pages") or []


def extract_text_from_sections(sections: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        if heading.lower() in SKIP_HEADINGS:
            continue
        content = section.get("content") or []
        for line in content:
            line = normalize_whitespace(line)
            if line:
                lines.append(line)
    return "\n".join(lines)


def extract_text(payload: Dict[str, Any]) -> str:
    sections = extract_sections(payload)
    if sections:
        return extract_text_from_sections(sections)

    pages = extract_pages(payload)
    if pages:
        lines: List[str] = []
        for page in pages:
            text = normalize_whitespace(page.get("text", ""))
            if text:
                lines.append(text)
        return "\n".join(lines)

    return ""


def keyword_tokens(value: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in {"and", "the", "for", "with", "from", "that"}
    ]


def keyword_is_relevant(keyword: str, context_text: str) -> bool:
    normalized = normalize_whitespace(keyword).lower().strip(".,;:- ")
    if not normalized or normalized in KEYWORD_BLOCKLIST:
        return False

    tokens = keyword_tokens(normalized)
    if not tokens:
        return False
    if "top" in tokens or len(tokens) > 4:
        return False

    context = context_text.lower()
    matched_tokens = [token for token in tokens if token in context]
    has_legal_token = any(token in LEGAL_KEYWORD_WHITELIST for token in tokens)
    has_strong_legal_token = any(
        token in LEGAL_KEYWORD_WHITELIST and token not in WEAK_LEGAL_KEYWORDS
        for token in tokens
    )

    if not has_legal_token or not has_strong_legal_token:
        return False
    if len(tokens) == 1:
        return bool(matched_tokens)
    return bool(matched_tokens) and len(matched_tokens) >= min(2, len(tokens))


def extract_keywords(sections: List[Dict[str, Any]], context_text: str = "") -> List[str]:
    keywords: List[str] = []
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        if heading.lower() not in KEYWORD_HEADINGS:
            continue
        for item in section.get("content") or []:
            item = normalize_whitespace(str(item))
            if keyword_is_relevant(item, context_text):
                keywords.append(item)
    return unique_preserve(keywords)[:8]


def extract_article_number(title: str, sections: List[Dict[str, Any]]) -> Optional[str]:
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        match = re.match(r"^([0-9]+[A-Za-z]*)\.\s+", heading)
        if match:
            return match.group(1)
    match = re.search(r"\bArticle\s+([0-9]+[A-Za-z]*)\b", title, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def extract_section_number_title(heading: str) -> Tuple[Optional[str], Optional[str]]:
    heading = normalize_whitespace(heading)
    match = re.match(r"^([0-9]+[A-Za-z]*)\.\s*(.+)$", heading)
    if match:
        return match.group(1), match.group(2).strip("- ")
    match = re.match(r"^Section\s+([0-9]+[A-Za-z]*)\b\s*(.*)$", heading, re.IGNORECASE)
    if match:
        title = match.group(2).strip("- ") or None
        return match.group(1), title
    return None, None


def extract_status(text: str) -> Optional[str]:
    lowered = text.lower()
    if "repeal" in lowered:
        return "Repealed"
    if "amend" in lowered:
        return "Amended"
    return None


def extract_editorial_commentary(sections: List[Dict[str, Any]]) -> Optional[str]:
    commentary_lines: List[str] = []
    for section in sections:
        for line in section.get("content") or []:
            if "editorial comment" in line.lower():
                commentary_lines.append(normalize_whitespace(line))
    commentary = " ".join(commentary_lines).strip()
    return commentary or None


def extract_lines(sections: List[Dict[str, Any]], limit: int = 40) -> List[str]:
    lines: List[str] = []
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        if heading.lower() in SKIP_HEADINGS:
            continue
        for line in section.get("content") or []:
            line = normalize_whitespace(line)
            if line:
                lines.append(line)
            if len(lines) >= limit:
                return lines
    return lines


def extract_lines_from_text(text: str, limit: int = 6) -> List[str]:
    if not text:
        return []
    parts = [normalize_whitespace(line) for line in text.split("\n")]
    return [part for part in parts if part][:limit]


def parse_date_from_text(text: str) -> Optional[date]:
    match = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3))
        month = MONTHS.get(month_name)
        if month:
            return date(year, month, day)

    match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        if year < 100:
            year += 1900
        try:
            return date(year, month, day)
        except ValueError:
            return None

    return None


def extract_date_from_text(title: str, sections: List[Dict[str, Any]]) -> Optional[date]:
    title_date = parse_date_from_text(title)
    if title_date:
        return title_date

    for line in [section.get("heading", "") for section in sections]:
        heading_date = parse_date_from_text(str(line))
        if heading_date:
            return heading_date

    for line in extract_lines(sections, limit=50):
        line_date = parse_date_from_text(line)
        if line_date:
            return line_date

    return None


def extract_court(sections: List[Dict[str, Any]]) -> Optional[str]:
    court_markers = ["high court", "supreme court", "district court", "tribunal", "court"]
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        lowered = heading.lower()
        if any(marker in lowered for marker in court_markers):
            return heading

    for line in extract_lines(sections, limit=30):
        lowered = line.lower()
        if any(marker in lowered for marker in court_markers):
            return line

    return None


def split_judge_names(value: str) -> List[str]:
    cleaned = value.replace(" and ", ", ")
    parts = [normalize_whitespace(part) for part in cleaned.split(",")]
    return [part for part in parts if part]


def extract_judges(sections: List[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        lowered = heading.lower()
        if lowered.startswith("bench:") or lowered.startswith("author:") or lowered.startswith("coram:"):
            value = heading.split(":", 1)[1].strip()
            names.extend(split_judge_names(value))
        elif lowered == "bench" and section.get("content"):
            for line in section.get("content") or []:
                names.extend(split_judge_names(line))

    return unique_preserve(names)


def extract_case_summary(sections: List[Dict[str, Any]]) -> Optional[str]:
    lines = extract_lines(sections, limit=6)
    if not lines:
        return None
    summary = " ".join(lines[:2])
    return summary[:400].strip() or None


def extract_case_lines(sections: List[Dict[str, Any]], limit: Optional[int] = None) -> List[str]:
    lines: List[str] = []
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        heading_lower = heading.lower()
        if heading_lower in SKIP_HEADINGS or heading_lower in NOISE_TEXT:
            continue
        if heading:
            lines.append(heading)
        for line in section.get("content") or []:
            line = normalize_whitespace(line)
            if line.lower() in NOISE_TEXT:
                continue
            if line:
                lines.append(line)
            if limit and len(lines) >= limit:
                return lines[:limit]
    return lines


def strip_page_markers(text: str) -> str:
    text = re.sub(r"\bPage\s+\d+\s*(?:/|of)\s*\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[A-Z]{1,8}\s+No\.\s*[\w./-]+\b", " ", text)
    return normalize_whitespace(text)


def join_case_lines(lines: List[str], max_chars: int = 1800) -> Optional[str]:
    cleaned = [strip_page_markers(line) for line in lines if strip_page_markers(line)]
    if not cleaned:
        return None
    text = " ".join(cleaned)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rsplit(" ", 1)[0].strip() + "..."


def is_argument_line(line: str) -> bool:
    lowered = line.lower()
    return any(
        marker in lowered
        for marker in (
            "learned counsel",
            "counsel for",
            "submitted",
            "contended",
            "argued",
            "urged",
            "pleaded",
            "averred",
            "it is the case of",
            "it was submitted",
        )
    )


def is_reasoning_line(line: str) -> bool:
    lowered = line.lower()
    return any(
        marker in lowered
        for marker in (
            "in view of",
            "therefore",
            "accordingly",
            "we hold",
            "i hold",
            "this court is of",
            "court is of",
            "it is clear",
            "it is evident",
            "it follows",
            "we are of the view",
            "i am of the view",
            "for the reasons",
            "no merit",
            "cannot be accepted",
            "liable to be",
            "not maintainable",
            "settled law",
        )
    )


def is_verdict_line(line: str) -> bool:
    lowered = line.lower()
    return any(
        marker in lowered
        for marker in (
            "appeal is allowed",
            "appeals are allowed",
            "appeal allowed",
            "petition is allowed",
            "petitions are allowed",
            "suit is decreed",
            "suit stands decreed",
            "appeal is dismissed",
            "appeals are dismissed",
            "appeal dismissed",
            "petition is dismissed",
            "petitions are dismissed",
            "petition stands dismissed",
            "petitions stands dismissed",
            "suit is dismissed",
            "suit stands dismissed",
            "suit filed by plaintiff is dismissed",
            "suit filed by the plaintiff is dismissed",
            "application is dismissed",
            "application stands dismissed",
            "revision petition is allowed",
            "revision petition is dismissed",
            "writ petition is allowed",
            "writ petition is dismissed",
            "is disposed of",
            "are disposed of",
            "stands disposed",
            "is set aside",
            "are set aside",
            "hereby set aside",
            "no order as to costs",
            "ordered accordingly",
            "decree is confirmed",
            "decree is set aside",
        )
    )


def extract_winner_role(text: str) -> Optional[str]:
    lowered = text.lower()
    if "partly allowed" in lowered or "partially allowed" in lowered:
        return "mixed"
    if any(
        phrase in lowered
        for phrase in (
            "appeal is allowed",
            "appeals are allowed",
            "appeal allowed",
            "petition is allowed",
            "petitions are allowed",
            "revision petition is allowed",
            "writ petition is allowed",
            "suit is decreed",
            "suit stands decreed",
            "decreed as prayed",
        )
    ):
        return "plaintiff_appellant"
    if any(
        phrase in lowered
        for phrase in (
            "appeal is dismissed",
            "appeals are dismissed",
            "appeal dismissed",
            "appeals fail",
            "appeal fails",
            "petition is dismissed",
            "petitions are dismissed",
            "petition stands dismissed",
            "petitions stands dismissed",
            "revision petition is dismissed",
            "writ petition is dismissed",
            "suit is dismissed",
            "suit stands dismissed",
            "suit filed by plaintiff is dismissed",
            "suit filed by the plaintiff is dismissed",
            "application is dismissed",
            "application stands dismissed",
        )
    ):
        return "defendant_respondent"
    return None


def extract_procedural_history(lines: List[str]) -> Optional[str]:
    selected: List[str] = []
    for line in lines[:45]:
        lowered = line.lower()
        if is_reasoning_line(line) or is_verdict_line(line):
            continue
        if (
            re.match(r"^\d+[\).]\s+", line)
            or any(marker in lowered for marker in ("filed", "suit", "appeal", "petition", "plaintiff", "defendant", "appellant", "respondent", "trial court", "high court"))
        ):
            selected.append(line)
        if len(selected) >= 8:
            break
    return join_case_lines(selected, max_chars=1600)


def extract_court_reasoning(lines: List[str]) -> Optional[str]:
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
    return join_case_lines(reasoning[:8], max_chars=2000)


def extract_verdict_order(lines: List[str]) -> Optional[str]:
    verdicts = [line for line in lines if is_verdict_line(line)]
    if verdicts:
        return join_case_lines(verdicts[-4:], max_chars=1200)
    tail = [line for line in lines[-8:] if line]
    return join_case_lines(tail[-3:], max_chars=900)


def extract_plain_english_summary(
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
    return join_case_lines(parts, max_chars=1400)


def extract_case_timeline(lines: List[str]) -> List[Tuple[Optional[date], str]]:
    events: List[Tuple[Optional[date], str]] = []
    seen = set()
    for line in lines:
        event_date = parse_date_from_text(line)
        if not event_date:
            continue
        event = strip_page_markers(line)
        if not event or event in seen:
            continue
        seen.add(event)
        events.append((event_date, event[:500]))
        if len(events) >= 12:
            break
    return events


def extract_case_arguments(lines: List[str]) -> List[Tuple[str, str]]:
    arguments: List[Tuple[str, str]] = []
    for line in lines:
        if not is_argument_line(line):
            continue
        lowered = line.lower()
        if any(role in lowered for role in ("defendant", "respondent", "revenue")):
            party_role = "defendant_respondent"
        else:
            party_role = "plaintiff_appellant"
        arguments.append((party_role, strip_page_markers(line)[:700]))
        if len(arguments) >= 12:
            break
    return arguments


def extract_objective(sections: List[Dict[str, Any]]) -> Optional[str]:
    for section in sections:
        heading = normalize_whitespace(section.get("heading", "")).lower()
        if "object" in heading and "reason" in heading:
            lines = [normalize_whitespace(line) for line in section.get("content") or [] if line]
            objective = " ".join(lines).strip()
            if objective:
                return objective
    return None


def extract_extent(sections: List[Dict[str, Any]]) -> Optional[str]:
    for section in sections:
        for line in section.get("content") or []:
            if "extends to" in line.lower():
                return normalize_whitespace(line)
    return None


def extract_citation(sections: List[Dict[str, Any]]) -> Optional[str]:
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        if heading.lower().startswith("equivalent citations") or heading.lower().startswith("citation"):
            lines = [normalize_whitespace(line) for line in section.get("content") or [] if line]
            if lines:
                return " ".join(lines).strip()
            if ":" in heading:
                return heading.split(":", 1)[1].strip()
    return None


def extract_case_parties(title: str) -> Tuple[Optional[str], Optional[str]]:
    patterns = [
        r"^(.*?)\s+vs\.?\s+(.*?)\s+on\b",
        r"^(.*?)\s+v\.?\s+(.*?)\s+on\b",
        r"^(.*?)\s+vs\.?\s+(.*)$",
        r"^(.*?)\s+v\.?\s+(.*)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            left = normalize_whitespace(match.group(1))
            right = normalize_whitespace(match.group(2))
            return left or None, right or None
    return None, None


def extract_parent_act_title(title: str) -> Optional[str]:
    match = re.search(r"\bin\s+(.*)$", title, re.IGNORECASE)
    if match:
        return normalize_whitespace(match.group(1))
    return None


def upsert_document(cur, doc_key: str, doc_type: str, title: str, source_file: Optional[str]) -> int:
    cur.execute(
        """
        INSERT INTO documents (doc_key, document_type, title, source_file, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (doc_key)
        DO UPDATE SET
          document_type = EXCLUDED.document_type,
          title = EXCLUDED.title,
          source_file = EXCLUDED.source_file,
          updated_at = NOW()
        RETURNING id;
        """,
        (doc_key, doc_type, title, source_file),
    )
    return int(cur.fetchone()[0])


def replace_article(cur, document_id: int, title: str, payload: Dict[str, Any]) -> None:
    sections = extract_sections(payload)
    article_number = extract_article_number(title, sections)
    status = extract_status(title)
    source_document = None
    if "constitution" in title.lower():
        source_document = "Constitution of India"

    original_text = None
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        if article_number and heading.startswith(f"{article_number}."):
            original_text = "\n".join(
                normalize_whitespace(line) for line in section.get("content") or [] if line
            ).strip() or None
            break
    if not original_text:
        original_text = extract_text(payload) or None

    editorial_commentary = extract_editorial_commentary(sections)
    keywords = extract_keywords(sections, f"{title} {original_text or ''}")

    cur.execute("DELETE FROM article_keywords WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM article_related_cases WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM article_amendments WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM article_metadata WHERE document_id = %s", (document_id,))

    cur.execute(
        """
        INSERT INTO article_metadata (
          document_id,
          source_document,
          article_number,
          status,
          original_text,
          editorial_commentary
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (document_id, source_document, article_number, status, original_text, editorial_commentary),
    )

    for keyword in keywords:
        cur.execute(
            "INSERT INTO article_keywords (document_id, keyword) VALUES (%s, %s)",
            (document_id, keyword),
        )


def replace_act(cur, document_id: int, payload: Dict[str, Any]) -> None:
    sections = extract_sections(payload)
    objective = extract_objective(sections)
    extent_application = extract_extent(sections)
    original_text = extract_text(payload) or None
    status = extract_status(objective or "") or extract_status(original_text or "")

    act_number = None
    enactment_date = None
    for line in extract_lines(sections, limit=20):
        match = re.search(r"\bAct\s+(\d+)\s+of\s+(\d{4})\b", line, re.IGNORECASE)
        if match:
            act_number = f"{match.group(1)} of {match.group(2)}"
        date_value = parse_date_from_text(line)
        if date_value and not enactment_date:
            enactment_date = date_value
    if not act_number and original_text:
        for line in extract_lines_from_text(original_text, limit=10):
            match = re.search(r"\bAct\s+(\d+)\s+of\s+(\d{4})\b", line, re.IGNORECASE)
            if match:
                act_number = f"{match.group(1)} of {match.group(2)}"
                break
    if not enactment_date and original_text:
        for line in extract_lines_from_text(original_text, limit=10):
            date_value = parse_date_from_text(line)
            if date_value:
                enactment_date = date_value
                break
    if not objective:
        for line in extract_lines(sections, limit=10):
            if "object" in line.lower() and "reason" in line.lower():
                objective = line
                break
    if not objective:
        fallback_lines = extract_lines(sections, limit=2)
        if not fallback_lines:
            fallback_lines = extract_lines_from_text(original_text or "", limit=2)
        objective = " ".join(fallback_lines).strip() if fallback_lines else None

    cur.execute("DELETE FROM act_section_keywords WHERE section_id IN (SELECT id FROM act_sections WHERE document_id = %s)", (document_id,))
    cur.execute("DELETE FROM act_sections WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM act_keywords WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM act_metadata WHERE document_id = %s", (document_id,))

    cur.execute(
        """
        INSERT INTO act_metadata (
          document_id,
                    act_number,
                    enactment_date,
                    status,
          objective,
          extent_application,
          original_text
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
                (document_id, act_number, enactment_date, status, objective, extent_application, original_text),
    )

    section_index = 0
    if not sections and original_text:
        sections = [{"heading": "preamble", "level": 0, "content": extract_lines_from_text(original_text, limit=20)}]
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        if heading.lower() in SKIP_HEADINGS:
            continue
        content_lines = [normalize_whitespace(line) for line in section.get("content") or [] if line]
        if not content_lines:
            continue
        section_number, section_title = extract_section_number_title(heading)
        original_text = "\n".join(content_lines).strip() or None

        cur.execute(
            """
            INSERT INTO act_sections (
              document_id,
              section_index,
              section_number,
              section_title,
              original_text,
              plain_english_explanation
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (document_id, section_index, section_number, section_title, original_text, None),
        )
        section_index += 1


def replace_section(cur, document_id: int, payload: Dict[str, Any], title: str) -> None:
    sections = extract_sections(payload)
    main_heading = None
    for section in sections:
        heading = normalize_whitespace(section.get("heading", ""))
        if heading and heading.lower() not in SKIP_HEADINGS and not heading.lower().startswith("section"):
            main_heading = heading
            break
    if not main_heading:
        main_heading = title

    section_number, section_title = extract_section_number_title(main_heading)
    parent_act_title = extract_parent_act_title(title)
    original_text = extract_text(payload) or None

    cur.execute("DELETE FROM section_metadata WHERE document_id = %s", (document_id,))
    cur.execute(
        """
        INSERT INTO section_metadata (
          document_id,
          parent_act_title,
          section_number,
          section_title,
          original_text
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (document_id, parent_act_title, section_number, section_title, original_text),
    )


def replace_case(cur, document_id: int, payload: Dict[str, Any], title: str) -> None:
    sections = extract_sections(payload)
    case_lines = extract_case_lines(sections)
    citation = extract_citation(sections)
    court = extract_court(sections)
    date_of_judgment = extract_date_from_text(title, sections)
    original_text = extract_text(payload) or None
    keywords = extract_keywords(sections, f"{title} {original_text or ''}")
    judges = extract_judges(sections)
    dispute_summary = extract_case_summary(sections)
    if not dispute_summary and original_text:
        summary_lines = extract_lines_from_text(original_text, limit=3)
        dispute_summary = " ".join(summary_lines).strip() if summary_lines else None
    winner_role = extract_winner_role(original_text or "")
    procedural_history = extract_procedural_history(case_lines)
    court_reasoning = extract_court_reasoning(case_lines)
    verdict_order = extract_verdict_order(case_lines)
    if not winner_role and verdict_order:
        winner_role = extract_winner_role(verdict_order)
    plain_english_translation = extract_plain_english_summary(
        title,
        dispute_summary,
        verdict_order,
        winner_role,
    )
    timeline = extract_case_timeline(case_lines)
    arguments = extract_case_arguments(case_lines)

    plaintiff, defendant = extract_case_parties(title)

    cur.execute("DELETE FROM case_related_sections WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM case_related_acts WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM case_keywords WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM case_timeline WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM case_arguments WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM case_parties WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM case_judges WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM case_metadata WHERE document_id = %s", (document_id,))

    cur.execute(
        """
        INSERT INTO case_metadata (
          document_id,
          citation,
          court,
          date_of_judgment,
          jurisdiction,
          dispute_summary,
          procedural_history,
          court_reasoning,
          verdict_order,
          plain_english_translation,
          winner_role,
          original_text
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            document_id,
            citation,
            court,
            date_of_judgment,
            None,
            dispute_summary,
            procedural_history,
            court_reasoning,
            verdict_order,
            plain_english_translation,
            winner_role,
            original_text,
        ),
    )

    if plaintiff:
        cur.execute(
            "INSERT INTO case_parties (document_id, party_role, party_name) VALUES (%s, %s, %s)",
            (document_id, "plaintiff_appellant", plaintiff),
        )
    if defendant:
        cur.execute(
            "INSERT INTO case_parties (document_id, party_role, party_name) VALUES (%s, %s, %s)",
            (document_id, "defendant_respondent", defendant),
        )

    for name in judges:
        cur.execute(
            "INSERT INTO case_judges (document_id, judge_name) VALUES (%s, %s)",
            (document_id, name),
        )

    for party_role, argument in arguments:
        cur.execute(
            "INSERT INTO case_arguments (document_id, party_role, argument) VALUES (%s, %s, %s)",
            (document_id, party_role, argument),
        )

    for event_date, event_text in timeline:
        cur.execute(
            "INSERT INTO case_timeline (document_id, event_date, event_text) VALUES (%s, %s, %s)",
            (document_id, event_date, event_text),
        )

    for keyword in keywords:
        cur.execute(
            "INSERT INTO case_keywords (document_id, keyword) VALUES (%s, %s)",
            (document_id, keyword),
        )


def load_all() -> Tuple[int, int, int, int, int]:
    load_env(ENV_PATH)
    dsn = build_dsn()
    total_docs = 0
    total_articles = 0
    total_acts = 0
    total_cases = 0
    total_sections = 0

    with psycopg2.connect(dsn) as conn:
        ensure_schema(conn)
        for json_path in iter_json_files():
            rel_path = json_path.relative_to(PROPERTY_RIGHTS_DIR)
            payload = load_json(json_path)
            raw_title = payload.get("title") or json_path.stem
            title = normalize_whitespace(str(raw_title)).lstrip("\ufeff")
            doc_type = detect_document_type(rel_path, title)
            source_file = payload.get("source_file")

            with conn.cursor() as cur:
                document_id = upsert_document(cur, rel_path.as_posix(), doc_type, title, source_file)

                if doc_type == "article":
                    replace_article(cur, document_id, title, payload)
                    total_articles += 1
                elif doc_type == "act":
                    replace_act(cur, document_id, payload)
                    total_acts += 1
                elif doc_type == "case":
                    replace_case(cur, document_id, payload, title)
                    total_cases += 1
                elif doc_type == "section":
                    replace_section(cur, document_id, payload, title)
                    total_sections += 1

                total_docs += 1
            conn.commit()

    return total_docs, total_articles, total_acts, total_cases, total_sections


def main() -> None:
    docs, articles, acts, cases, sections = load_all()
    print("Load complete.")
    print(f"Documents: {docs}")
    print(f"Articles: {articles}")
    print(f"Acts: {acts}")
    print(f"Cases: {cases}")
    print(f"Sections: {sections}")


if __name__ == "__main__":
    main()
