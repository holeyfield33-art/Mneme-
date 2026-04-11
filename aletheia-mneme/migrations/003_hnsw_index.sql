CREATE INDEX memories_embedding_hnsw ON memories
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
