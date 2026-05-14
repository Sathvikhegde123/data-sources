import json
import re
from pathlib import Path
from typing import Any, Tuple


BASE_DIR = Path(__file__).resolve().parent
TARGET_DIR = BASE_DIR / "parsed_json_new" / "property_rights"

NOISE_LINES = {
    "login required",
    "you need to be signed in to use the ai legal assistant for this judgment.",
    "ask questions about the document",
    "get legal explanations and summaries",
    "save your chat history",
    "new user? sign up here",
    "indian kanoon - search engine for indian law",
    "search",
    "main navigation",
    "mobile navigation",
    "legal document view",
    "tools for analyzing structure and cite text of judgments",
    "unlock advanced research with prism ai",
    "document options",
    "related ai tags, queries and research notes",
    "prism ai",
    "sign up here",
    "upgrade to premium",
}

NOISE_PATTERNS = [
    re.compile(r"(?im)^\s*Login Required\s*$"),
    re.compile(
        r"(?im)^\s*You need to be signed in to use the AI legal assistant for this judgment\.\s*$"
    ),
    re.compile(r"(?im)^\s*Ask questions about the document\s*$"),
    re.compile(r"(?im)^\s*Get legal explanations and summaries\s*$"),
    re.compile(r"(?im)^\s*Save your chat history\s*$"),
    re.compile(r"(?im)^\s*New user\? Sign up here\s*$"),
    re.compile(r"(?im)^\s*Sign up here\s*$"),
    re.compile(r"(?im)^\s*Prism AI\s*$"),
    re.compile(r"(?im)^\s*Upgrade to Premium\s*$"),
    re.compile(
        r"(?im)^\s*Unlock Advanced Research with PRISM AI.*?Upgrade to Premium\s*$"
    ),
]


def normalize_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def clean_text(value: str) -> Tuple[str, int]:
    original = value
    for pattern in NOISE_PATTERNS:
        value = pattern.sub("", value)
    lines = value.splitlines()
    kept = [line for line in lines if normalize_line(line) not in NOISE_LINES]
    value = "\n".join(kept)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return value, int(value != original)


def clean_value(value: Any) -> Tuple[Any, int]:
    if isinstance(value, str):
        return clean_text(value)

    if isinstance(value, list):
        changed = 0
        cleaned_items = []
        for item in value:
            cleaned, item_changed = clean_value(item)
            changed += item_changed
            if isinstance(cleaned, str) and not cleaned.strip():
                continue
            if isinstance(cleaned, dict) and should_drop_dict(cleaned):
                changed += 1
                continue
            cleaned_items.append(cleaned)
        return cleaned_items, changed

    if isinstance(value, dict):
        changed = 0
        cleaned_dict = {}
        for key, item in value.items():
            cleaned, item_changed = clean_value(item)
            changed += item_changed
            cleaned_dict[key] = cleaned
        return cleaned_dict, changed

    return value, 0


def should_drop_dict(value: dict) -> bool:
    text = value.get("text")
    heading = value.get("heading")
    label = text if isinstance(text, str) else heading if isinstance(heading, str) else ""
    normalized = normalize_line(label)
    if normalized in NOISE_LINES:
        return True
    if normalized.startswith("unlock advanced research with prism ai"):
        return True
    if value.get("href") in {"", "#"} and not normalized:
        return True
    return False


def main() -> None:
    total_files = 0
    changed_files = 0
    changed_values = 0

    for path in sorted(TARGET_DIR.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cleaned, changes = clean_value(payload)
        total_files += 1
        if changes:
            path.write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed_files += 1
            changed_values += changes

    print(f"Scanned files: {total_files}")
    print(f"Changed files: {changed_files}")
    print(f"Changed text values: {changed_values}")


if __name__ == "__main__":
    main()
