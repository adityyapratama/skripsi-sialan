-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop existing table
DROP TABLE IF EXISTS documents CASCADE;

-- Main documents table
CREATE TABLE documents (
  -- Primary key
  id                SERIAL PRIMARY KEY,

  -- Identitas dokumen (diambil dari HTML halaman detail, tanpa OCR)
  title             TEXT NOT NULL,
  author            TEXT,
  supervisor        TEXT,              -- Dosen Pembimbing
  program_study     TEXT NOT NULL,     -- Label utama untuk classifier IndoBERT
  faculty           TEXT,              -- Contoh: "Fakultas Vokasi"
  pub_year          INTEGER,           -- Tahun terbit, contoh: 2025
  subject_keywords  TEXT,              -- Field "Subjek" dari ir.unair.ac.id (keyword bebas)
  language          TEXT DEFAULT 'Indonesia',

  -- Teks hasil OCR (input model AI)
  abstract_text     TEXT,              -- Hasil OCR halaman abstrak — input utama SBERT
  bab1_text         TEXT,              -- Hasil OCR BAB 1 — konteks tambahan (opsional)

  -- Output model AI
  label             TEXT,              -- Hasil prediksi IndoBERT (program_study yang diprediksi)
  label_confidence  FLOAT,             -- Confidence score prediksi (0.0 - 1.0)

  -- Embedding untuk semantic search
  embedding_search  vector(768),       -- Vektor dari SBERT (paraphrase-multilingual-mpnet-base-v2)

  -- URL navigasi ke sistem resmi Unair
  url_source        TEXT UNIQUE NOT NULL,  -- URL halaman detail: ir.unair.ac.id/detail-opac?id=...
  url_baca_online   TEXT,                  -- URL Flip PDF reader (tombol "Baca Online")

  -- Status proses scraping
  ocr_status        TEXT DEFAULT 'pending',  -- nilai: 'pending' | 'done' | 'failed'

  -- Timestamp
  created_at        TIMESTAMP DEFAULT NOW()
);

-- Index untuk semantic search (HNSW lebih baik dari IVFFlat untuk dataset < 100k)
CREATE INDEX idx_embedding_hnsw
  ON documents
  USING hnsw (embedding_search vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Index untuk filter pencarian
CREATE INDEX idx_label         ON documents (label);
CREATE INDEX idx_program_study ON documents (program_study);
CREATE INDEX idx_faculty       ON documents (faculty);
CREATE INDEX idx_pub_year      ON documents (pub_year);
CREATE INDEX idx_ocr_status    ON documents (ocr_status);
