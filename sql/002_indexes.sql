CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_chunks_book_id ON chunks(book_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page_start ON chunks(page_start);

-- FTS index
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON chunks USING GIN (fts);

-- array terms acceleration
CREATE INDEX IF NOT EXISTS idx_chunks_keywords_gin ON chunks USING GIN (keywords);

-- HNSW Vector Index (Better than ivfflat for this dataset)
-- Drop the old ivfflat index if it exists, though IF EXISTS handles that for creation, we'd better drop first just in case.
DROP INDEX IF EXISTS idx_chunks_embedding;
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 128);
