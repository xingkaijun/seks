-- pg_jieba 已移除，改用 simple（对英文按空格切词足够）
-- 若已有旧列则先删除再重建
ALTER TABLE chunks DROP COLUMN IF EXISTS fts;

ALTER TABLE chunks ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(chunk_text, ''))
  ) STORED;

DROP INDEX IF EXISTS idx_chunks_fts;
DROP INDEX IF EXISTS idx_chunks_fts_gin;
CREATE INDEX idx_chunks_fts_gin ON chunks USING gin (fts);
