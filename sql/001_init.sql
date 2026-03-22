CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS books (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT,
  edition TEXT,
  publish_year INT,
  language TEXT DEFAULT 'zh',
  source_type TEXT,
  domain_tags TEXT[],
  file_path TEXT NOT NULL,
  file_hash TEXT UNIQUE,
  page_count INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
  id BIGSERIAL PRIMARY KEY,
  book_id BIGINT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  chapter TEXT,
  section TEXT,
  page_start INT,
  page_end INT,
  chunk_index INT NOT NULL,
  chunk_text TEXT NOT NULL,
  token_count INT,
  keywords TEXT[],
  embedding vector(384),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS queries (
  id BIGSERIAL PRIMARY KEY,
  question TEXT NOT NULL,
  answer TEXT,
  retrieved_chunk_ids BIGINT[],
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS fts tsvector
GENERATED ALWAYS AS (
  to_tsvector('simple', coalesce(chunk_text, ''))
) STORED;
