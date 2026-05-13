import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"


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


load_env(ENV_PATH)
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
