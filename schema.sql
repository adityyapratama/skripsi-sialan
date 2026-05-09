-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop table for reset
DROP TABLE IF EXISTS raw_documents CASCADE;

-- Table for raw documents
CREATE TABLE raw_documents (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    program_study TEXT,
    subject TEXT, -- Classification label
    abstract_text TEXT,
    bab1_text TEXT,
    embedding vector(768), -- Embedding size for IndoBERT Base (768)
    url_source TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for similarity search
CREATE INDEX ON raw_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
