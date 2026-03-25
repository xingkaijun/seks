-- 启用 pg_jieba 扩展
CREATE EXTENSION IF NOT EXISTS pg_jieba;

-- 删除旧的基于 simple 空格划分的无用检索列
ALTER TABLE chunks DROP COLUMN IF EXISTS fts;

-- 重新生成基于高质量中文分词词典的检索列
ALTER TABLE chunks ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('jiebacfg', coalesce(chunk_text, ''))
  ) STORED;

-- 重建加速索引
DROP INDEX IF EXISTS idx_chunks_fts;
CREATE INDEX idx_chunks_fts_gin ON chunks USING gin (fts);
