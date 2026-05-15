import json
import os
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor
import google.generativeai as genai

from legal_property_rag_pipeline.legal_property_rag import LegalPropertyRAG

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
RAG_MANIFEST_PATH = BASE_DIR / "legal_property_rag_pipeline" / "property_rights_rag_manifest.json"
PARSED_JSON_BASE = BASE_DIR / "parsed_json_new" / "property_rights"


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


def fetch_all(query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
    with psycopg2.connect(build_dsn()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def fetch_one(query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
    with psycopg2.connect(build_dsn()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
    return dict(row) if row else None


def normalize_json_fields(payload: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if value is None:
            payload[key] = [] if key.endswith("s") else None
    return payload


def load_rag_records() -> List[Dict[str, Any]]:
    if not RAG_MANIFEST_PATH.exists():
        raise FileNotFoundError("RAG manifest not found")
    manifest = json.loads(RAG_MANIFEST_PATH.read_text(encoding="utf-8"))
    records = manifest.get("records", [])
    if not isinstance(records, list):
        raise ValueError("RAG manifest records are invalid")
    return records


@lru_cache(maxsize=1)
def get_rag_record_map() -> Dict[str, Dict[str, Any]]:
    records = load_rag_records()
    record_map: Dict[str, Dict[str, Any]] = {}
    for record in records:
        record_id = record.get("id")
        if record_id:
            record_map[str(record_id)] = record
    return record_map


def resolve_parsed_json_path(relative_path: str) -> Path:
    base = PARSED_JSON_BASE.resolve()
    target = (base / relative_path).resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid RAG path")
    return target


@lru_cache(maxsize=1)
def get_rag() -> LegalPropertyRAG:
    records = load_rag_records()
    return LegalPropertyRAG(records)


class RagRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=4000)
    top_k: int = Field(5, ge=1, le=20)
    doc_type_filter: Optional[str] = None


class ExplainRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=4000)
    document_title: str = Field(..., max_length=500)
    document_summary: Optional[str] = Field(None, max_length=2000)
    case_metadata: Optional[Dict[str, Any]] = None
    full_document: Optional[Dict[str, Any]] = None


load_env(ENV_PATH)

# Configure Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI(title="Property Rights API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/rag")
def rag_search(payload: RagRequest) -> Dict[str, Any]:
    query_text = payload.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        rag = get_rag()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="RAG manifest not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to load RAG pipeline") from exc

    results = rag.query(
        query_text,
        top_k=payload.top_k,
        doc_type_filter=payload.doc_type_filter,
    )

    return {
        "query": query_text,
        "top_k": payload.top_k,
        "doc_type_filter": payload.doc_type_filter,
        "results": [doc.to_dict() for doc in results],
    }


@app.get("/api/rag/records/{record_id}")
def rag_record_detail(record_id: str) -> Dict[str, Any]:
    record = get_rag_record_map().get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="RAG record not found")

    locations = record.get("locations", {}) if isinstance(record.get("locations"), dict) else {}
    relative_path = locations.get("relative_path")
    if not relative_path:
        raise HTTPException(status_code=404, detail="RAG record missing file path")

    file_path = resolve_parsed_json_path(relative_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Parsed JSON file not found")

    parsed_json = json.loads(file_path.read_text(encoding="utf-8"))
    return {
        "record": record,
        "parsed_json": parsed_json,
    }


@app.post("/api/explain")
def explain_relevance(payload: ExplainRequest) -> Dict[str, Any]:
    """
    Use Gemini to explain how a retrieved document is relevant to the user's query.
    Sends full document content for better context, but intelligently truncates to avoid token limits.
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Gemini API key not configured")

    try:
        # Extract key document content from full_document JSON
        full_doc_context = ""
        if payload.full_document:
            doc = payload.full_document
            structured = doc.get("structured_data", {})
            case_meta = structured.get("case_metadata", {})
            
            # Build rich context from the full document
            context_lines = []
            
            # Add case-specific details
            if case_meta.get("dispute_summary"):
                context_lines.append(f"Dispute Summary:\n{case_meta['dispute_summary'][:1000]}")
            
            if case_meta.get("plain_english_translation"):
                context_lines.append(f"Plain English:\n{case_meta['plain_english_translation'][:1000]}")
            
            if case_meta.get("court_reasoning"):
                context_lines.append(f"Court Reasoning:\n{case_meta['court_reasoning'][:800]}")
            
            if case_meta.get("verdict_order"):
                context_lines.append(f"Verdict:\n{case_meta['verdict_order'][:600]}")
            
            if case_meta.get("parties"):
                parties = case_meta.get("parties", [])
                if parties:
                    party_str = ", ".join([f"{p.get('role')}: {p.get('name')}" for p in parties if isinstance(p, dict)])
                    if party_str:
                        context_lines.append(f"Parties: {party_str}")
            
            # Add raw text if available (limited)
            raw_text = doc.get("raw_text", "")
            if raw_text:
                context_lines.append(f"Key Content:\n{raw_text[:1200]}")
            
            full_doc_context = "\n\n".join(context_lines)
        
        # Build the prompt with full document context
        # Unified relevance prompt: concise explanation of relevance (3-4 sentences)
        # Use the provided prompt template for both full-document and metadata-only cases.
        context_parts = []
        context_parts.append(f"User's Property Rights Scenario: {payload.query}")
        context_parts.append(f"Document Title: {payload.document_title}")
        if full_doc_context:
            context_parts.append(f"Document Content:\n{full_doc_context}")
        elif payload.document_summary:
            context_parts.append(f"Document Summary: {payload.document_summary}")
        elif payload.case_metadata and isinstance(payload.case_metadata, dict):
            meta = payload.case_metadata
            if meta.get("dispute_summary"):
                context_parts.append(f"Dispute: {meta['dispute_summary'][:500]}")
        context = "\n\n".join(context_parts)

        prompt = f"""Based on this information, explain in 3-4 sentences how this legal document/case is relevant to the user's property rights scenario.Only explain how its relevant.Do not give what does not match.

{context}

Provide a clear explanation of the relevance without legal jargon.Do not tell this document is not relevant.Only explain what is the similarity."""
        # prompt already constructed above

        # Try different model names as fallback
        models_to_try = ["gemini-2.5-flash"]
        response = None
        last_error = None
        
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                break  # Success, exit loop
            except Exception as e:
                last_error = e
                print(f"Model {model_name} failed: {str(e)}")
                continue
        
        if response is None:
            raise last_error or Exception("All Gemini models failed")
        
        # Handle different response formats
        explanation = None
        if hasattr(response, 'text'):
            explanation = response.text
        elif response.candidates:
            explanation = response.candidates[0].content.parts[0].text
        
        if not explanation or not explanation.strip():
            explanation = "This case may have relevance to your property rights scenario."
        
        return {
            "explanation": explanation.strip(),
            "status": "success"
        }
    
    except Exception as exc:
        import traceback
        error_detail = f"Gemini API error: {str(exc)}"
        print(f"Explain error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=error_detail
        ) from exc
        raise HTTPException(
            status_code=500, 
            detail=error_detail
        ) from exc


@app.get("/api/cases")
def list_cases() -> List[Dict[str, Any]]:
    query = """
        SELECT
          d.id AS document_id,
          d.title,
          m.citation,
          m.court,
          m.date_of_judgment,
          m.jurisdiction,
          m.dispute_summary,
          m.plain_english_translation,
          m.winner_role,
          COALESCE(
            (SELECT jsonb_object_agg(p.party_role, p.party_name) FROM case_parties p WHERE p.document_id = d.id),
            '{}'::jsonb
          ) AS parties,
          COALESCE(
            (SELECT array_agg(k.keyword ORDER BY k.id) FROM case_keywords k WHERE k.document_id = d.id),
            ARRAY[]::text[]
          ) AS keywords
        FROM documents d
        JOIN case_metadata m ON m.document_id = d.id
        WHERE d.document_type = 'case'
        ORDER BY d.id ASC;
    """
    return fetch_all(query)


@app.get("/api/cases/{document_id}")
def get_case(document_id: int) -> Dict[str, Any]:
    query = """
        SELECT
          d.id AS document_id,
          d.title,
          m.citation,
          m.court,
          m.date_of_judgment,
          m.jurisdiction,
          m.dispute_summary,
          m.procedural_history,
          m.court_reasoning,
          m.verdict_order,
          m.plain_english_translation,
          m.winner_role,
          m.original_text,
          COALESCE(
            (SELECT jsonb_object_agg(p.party_role, p.party_name) FROM case_parties p WHERE p.document_id = d.id),
            '{}'::jsonb
          ) AS parties,
          COALESCE(
            (SELECT array_agg(j.judge_name ORDER BY j.id) FROM case_judges j WHERE j.document_id = d.id),
            ARRAY[]::text[]
          ) AS judges,
          COALESCE(
            (SELECT jsonb_agg(jsonb_build_object('role', a.party_role, 'argument', a.argument) ORDER BY a.id)
             FROM case_arguments a WHERE a.document_id = d.id),
            '[]'::jsonb
          ) AS arguments,
          COALESCE(
            (SELECT jsonb_agg(jsonb_build_object('date', t.event_date, 'event', t.event_text) ORDER BY t.id)
             FROM case_timeline t WHERE t.document_id = d.id),
            '[]'::jsonb
          ) AS timeline,
          COALESCE(
            (SELECT array_agg(k.keyword ORDER BY k.id) FROM case_keywords k WHERE k.document_id = d.id),
            ARRAY[]::text[]
          ) AS keywords
        FROM documents d
        JOIN case_metadata m ON m.document_id = d.id
        WHERE d.id = %s;
    """
    row = fetch_one(query, (document_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return row


@app.get("/api/acts")
def list_acts() -> List[Dict[str, Any]]:
    query = """
        SELECT
          d.id AS document_id,
          d.title,
          m.act_number,
          m.enactment_date,
          m.status,
          m.objective,
          m.extent_application,
          COALESCE(
            (SELECT COUNT(*) FROM act_sections s WHERE s.document_id = d.id),
            0
          ) AS section_count,
          COALESCE(
            (SELECT array_agg(k.keyword ORDER BY k.id) FROM act_keywords k WHERE k.document_id = d.id),
            ARRAY[]::text[]
          ) AS keywords
        FROM documents d
        JOIN act_metadata m ON m.document_id = d.id
        WHERE d.document_type = 'act'
        ORDER BY d.id ASC;
    """
    return fetch_all(query)


@app.get("/api/acts/{document_id}")
def get_act(document_id: int) -> Dict[str, Any]:
    query = """
        SELECT
          d.id AS document_id,
          d.title,
          m.act_number,
          m.enactment_date,
          m.status,
          m.objective,
          m.extent_application,
          m.original_text,
          COALESCE(
            (SELECT jsonb_agg(jsonb_build_object(
                'section_number', s.section_number,
                'section_title', s.section_title,
                'original_text', s.original_text,
                'plain_english_explanation', s.plain_english_explanation
              ) ORDER BY s.section_index)
             FROM act_sections s WHERE s.document_id = d.id),
            '[]'::jsonb
          ) AS sections,
          COALESCE(
            (SELECT array_agg(k.keyword ORDER BY k.id) FROM act_keywords k WHERE k.document_id = d.id),
            ARRAY[]::text[]
          ) AS keywords
        FROM documents d
        JOIN act_metadata m ON m.document_id = d.id
        WHERE d.id = %s;
    """
    row = fetch_one(query, (document_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Act not found")
    return row


@app.get("/api/articles")
def list_articles() -> List[Dict[str, Any]]:
    query = """
        SELECT
          d.id AS document_id,
          d.title,
          m.source_document,
          m.article_number,
          m.status,
          COALESCE(
            (SELECT array_agg(k.keyword ORDER BY k.id) FROM article_keywords k WHERE k.document_id = d.id),
            ARRAY[]::text[]
          ) AS keywords
        FROM documents d
        JOIN article_metadata m ON m.document_id = d.id
        WHERE d.document_type = 'article'
        ORDER BY d.id ASC;
    """
    return fetch_all(query)


@app.get("/api/articles/{document_id}")
def get_article(document_id: int) -> Dict[str, Any]:
    query = """
        SELECT
          d.id AS document_id,
          d.title,
          m.source_document,
          m.article_number,
          m.status,
          m.original_text,
          m.editorial_commentary,
          COALESCE(
            (SELECT jsonb_agg(jsonb_build_object('amendment', a.amendment, 'effect', a.effect)
             ORDER BY a.amendment_index)
             FROM article_amendments a WHERE a.document_id = d.id),
            '[]'::jsonb
          ) AS amendments,
          COALESCE(
            (SELECT array_agg(k.keyword ORDER BY k.id) FROM article_keywords k WHERE k.document_id = d.id),
            ARRAY[]::text[]
          ) AS keywords
        FROM documents d
        JOIN article_metadata m ON m.document_id = d.id
        WHERE d.id = %s;
    """
    row = fetch_one(query, (document_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return row
