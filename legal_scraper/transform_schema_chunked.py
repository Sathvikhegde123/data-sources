import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from google import genai

# =========================================================
# CONFIG
# =========================================================

INPUT_DIR = Path("parsed_json/property_rights")
OUTPUT_DIR = Path("parsed_json_new")

MODEL_NAME = "gemini-2.5-flash"

BATCH_SIZE = 5

MAX_RETRIES = 5

# =========================================================
# LOAD ENV
# =========================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY missing")

client = genai.Client(api_key=API_KEY)

# =========================================================
# REQUIRED OUTPUT SCHEMA
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

        "case_metadata": {},
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

# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are an advanced Indian legal document extraction engine.

Your task:
- Read legal JSON documents carefully
- Extract ALL legally relevant information
- Preserve legal meaning exactly
- Preserve citations, sections, acts, judges, reasoning, timelines
- Maximize recall
- NEVER omit useful information

CRITICAL RULES:
- Return VALID JSON ONLY
- Maintain exact schema
- Fill ALL fields
- Use [] for missing arrays
- Use {} for missing objects
- Use "" for missing strings
- Never hallucinate
- Never add markdown
- Never explain output
"""

# =========================================================
# HELPERS
# =========================================================

def ensure_schema(data, schema):
    """
    recursively fills missing fields
    """

    if isinstance(schema, dict):

        if not isinstance(data, dict):
            data = {}

        result = {}

        for key, value in schema.items():

            result[key] = ensure_schema(
                data.get(key),
                value
            )

        return result

    elif isinstance(schema, list):

        if not isinstance(data, list):
            return []

        return data

    elif isinstance(schema, str):

        if data is None:
            return ""

        return str(data)

    return data


def clean_json_response(text: str):

    text = text.strip()

    if text.startswith("```"):

        text = text.split("```")[1]

        if text.startswith("json"):
            text = text[4:]

    return text.strip()


def detect_document_type(path_str):

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


# =========================================================
# LLM CALL
# =========================================================

def call_gemini(batch_payload):

    prompt = f"""
REQUIRED OUTPUT SCHEMA:

{json.dumps(REQUIRED_SCHEMA, indent=2, ensure_ascii=False)}

INPUT DOCUMENTS:

{json.dumps(batch_payload, ensure_ascii=False)}

TASK:
For EACH document:
- extract all legal information
- fill all schema fields
- preserve original json
- preserve raw text
- preserve legal reasoning
- preserve all sections and citations

Return STRICTLY this format:

[
  {{
    "document": {{}},
    "raw_text": "",
    "structured_data": {{}},
    "preserved_original_json": {{}}
  }}
]
"""

    for attempt in range(MAX_RETRIES):

        try:

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": SYSTEM_PROMPT + "\n\n" + prompt
                            }
                        ]
                    }
                ]
            )

            text = clean_json_response(response.text)

            parsed = json.loads(text)

            validated = []

            for item in parsed:

                validated.append(
                    ensure_schema(item, REQUIRED_SCHEMA)
                )

            return validated

        except Exception as e:

            print(f"Retry {attempt+1} failed")
            print(e)

            time.sleep(3)

    raise Exception("Gemini failed after retries")


# =========================================================
# LOAD FILES
# =========================================================

def load_json_files():

    json_files = list(INPUT_DIR.rglob("*.json"))

    loaded = []

    for file_path in json_files:

        try:

            with open(file_path, "r", encoding="utf-8") as f:

                data = json.load(f)

            loaded.append({
                "source_file": str(file_path),
                "document_type": detect_document_type(str(file_path)),
                "json_data": data
            })

        except Exception as e:

            print(f"Failed loading {file_path}")
            print(e)

    return loaded


# =========================================================
# BATCHING
# =========================================================

def create_batches(items, batch_size):

    batches = []

    for i in range(0, len(items), batch_size):

        batches.append(
            items[i:i + batch_size]
        )

    return batches


# =========================================================
# SAVE OUTPUTS
# =========================================================

def save_batch_outputs(outputs):

    for item in outputs:

        source_file = item["document"]["source_file"]

        if not source_file:
            continue

        relative = Path(source_file).name

        output_path = OUTPUT_DIR / relative

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(output_path, "w", encoding="utf-8") as f:

            json.dump(
                item,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(f"SAVED -> {output_path}")


# =========================================================
# MAIN PIPELINE
# =========================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    documents = load_json_files()

    print(f"TOTAL DOCUMENTS: {len(documents)}")

    batches = create_batches(
        documents,
        BATCH_SIZE
    )

    print(f"TOTAL BATCHES: {len(batches)}")

    for batch_index, batch in enumerate(batches):

        print("=" * 70)
        print(f"BATCH {batch_index+1}/{len(batches)}")

        try:

            outputs = call_gemini(batch)

            save_batch_outputs(outputs)

        except Exception as e:

            print(f"BATCH FAILED: {batch_index+1}")
            print(e)

    print("\nDONE")


# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":
    main()