-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Table for raw documents
CREATE TABLE IF NOT EXISTS raw_documents (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    program_study TEXT,
    subject TEXT, -- Classification label
    raw_text TEXT,
    cleaned_text TEXT,
    embedding vector(768), -- Embedding size for IndoBERT Base (768)
    url_source TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for similarity search
CREATE INDEX ON raw_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
