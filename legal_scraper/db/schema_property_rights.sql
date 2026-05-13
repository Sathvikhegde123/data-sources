DROP TABLE IF EXISTS case_related_sections CASCADE;
DROP TABLE IF EXISTS case_related_acts CASCADE;
DROP TABLE IF EXISTS case_keywords CASCADE;
DROP TABLE IF EXISTS case_timeline CASCADE;
DROP TABLE IF EXISTS case_arguments CASCADE;
DROP TABLE IF EXISTS case_parties CASCADE;
DROP TABLE IF EXISTS case_judges CASCADE;
DROP TABLE IF EXISTS case_metadata CASCADE;
DROP TABLE IF EXISTS section_metadata CASCADE;
DROP TABLE IF EXISTS act_section_keywords CASCADE;
DROP TABLE IF EXISTS act_sections CASCADE;
DROP TABLE IF EXISTS act_keywords CASCADE;
DROP TABLE IF EXISTS act_metadata CASCADE;
DROP TABLE IF EXISTS article_keywords CASCADE;
DROP TABLE IF EXISTS article_related_cases CASCADE;
DROP TABLE IF EXISTS article_amendments CASCADE;
DROP TABLE IF EXISTS article_metadata CASCADE;
DROP TABLE IF EXISTS documents CASCADE;

CREATE TABLE documents (
  id BIGSERIAL PRIMARY KEY,
  doc_key TEXT UNIQUE NOT NULL,
  document_type TEXT NOT NULL,
  title TEXT,
  source_file TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX documents_document_type_idx ON documents (document_type);
CREATE INDEX documents_title_idx ON documents (title);

CREATE TABLE article_metadata (
  document_id BIGINT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  source_document TEXT,
  article_number TEXT,
  status TEXT,
  original_text TEXT,
  editorial_commentary TEXT
);

CREATE TABLE article_amendments (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  amendment_index INTEGER NOT NULL,
  amendment TEXT,
  effect TEXT,
  UNIQUE (document_id, amendment_index)
);

CREATE TABLE article_related_cases (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  case_key TEXT NOT NULL
);

CREATE TABLE article_keywords (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  keyword TEXT NOT NULL
);

CREATE TABLE act_metadata (
  document_id BIGINT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  act_number TEXT,
  enactment_date DATE,
  status TEXT,
  objective TEXT,
  extent_application TEXT,
  original_text TEXT
);

CREATE TABLE act_sections (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  section_index INTEGER NOT NULL,
  section_number TEXT,
  section_title TEXT,
  original_text TEXT,
  plain_english_explanation TEXT,
  UNIQUE (document_id, section_index)
);

CREATE TABLE act_section_keywords (
  id BIGSERIAL PRIMARY KEY,
  section_id BIGINT NOT NULL REFERENCES act_sections(id) ON DELETE CASCADE,
  keyword TEXT NOT NULL
);

CREATE TABLE act_keywords (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  keyword TEXT NOT NULL
);

CREATE TABLE section_metadata (
  document_id BIGINT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  parent_act_title TEXT,
  section_number TEXT,
  section_title TEXT,
  original_text TEXT
);

CREATE TABLE case_metadata (
  document_id BIGINT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  citation TEXT,
  court TEXT,
  date_of_judgment DATE,
  jurisdiction TEXT,
  dispute_summary TEXT,
  procedural_history TEXT,
  court_reasoning TEXT,
  verdict_order TEXT,
  plain_english_translation TEXT,
  winner_role TEXT,
  original_text TEXT
);

CREATE TABLE case_judges (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  judge_name TEXT NOT NULL
);

CREATE TABLE case_parties (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  party_role TEXT NOT NULL,
  party_name TEXT NOT NULL
);

CREATE TABLE case_arguments (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  party_role TEXT NOT NULL,
  argument TEXT NOT NULL
);

CREATE TABLE case_timeline (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  event_date DATE,
  event_text TEXT
);

CREATE TABLE case_keywords (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  keyword TEXT NOT NULL
);

CREATE TABLE case_related_acts (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  act_key TEXT NOT NULL
);

CREATE TABLE case_related_sections (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  section_key TEXT NOT NULL
);
