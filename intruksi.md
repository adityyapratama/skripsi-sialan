# Instruksi untuk AI Agent — Refactor Scraper & Database

Kamu adalah AI coding agent. Tugasmu adalah melakukan refactor pada dua file:
`schema.sql` dan `scraper.py` sesuai instruksi di bawah ini.
Jangan ubah file lain kecuali disebutkan.

---

## TUGAS 1 — Ganti isi `schema.sql` sepenuhnya

Hapus seluruh isi `schema.sql` dan ganti dengan SQL berikut ini persis:

```sql
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
```

---

## TUGAS 2 — Refactor `scraper.py`

Lakukan perubahan berikut pada `scraper.py`. Jangan ubah logika OCR yang sudah ada kecuali yang disebutkan.

### 2a. Ganti nama tabel di semua query

Cari semua kemunculan `raw_documents` dan ganti menjadi `documents`.

### 2b. Ganti fungsi `get_existing_urls`

Ganti isi fungsi `get_existing_urls` menjadi:

```python
def get_existing_urls(db_conn):
    """Ambil daftar URL yang sudah ada di database agar tidak di-scrape ulang."""
    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT url_source FROM documents")
        existing = {row[0] for row in cursor.fetchall()}
        cursor.close()
        return existing
    except Exception as e:
        print(f"Gagal mengambil riwayat dokumen: {e}")
        return set()
```

### 2c. Ganti fungsi `get_existing_doc_ids`

```python
def get_existing_doc_ids(db_conn):
    """Ambil semua ID dokumen yang sudah ada untuk mencegah proses ulang."""
    existing_ids = set()
    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT url_source FROM documents WHERE url_source IS NOT NULL")
        for row in cursor.fetchall():
            url = row[0]
            if 'id=' in url:
                existing_ids.add(url.split('id=')[-1])
        cursor.close()
    except Exception as e:
        print(f"Gagal memuat history database: {e}")
    return existing_ids
```

### 2d. Ganti fungsi `scrape_metadata`

Ganti seluruh fungsi `scrape_metadata` dengan versi baru ini yang mengambil lebih banyak field:

```python
def scrape_metadata(soup):
    """
    Ekstraksi metadata dari halaman detail ir.unair.ac.id.
    Mengambil: title, author, supervisor, program_study, faculty,
               pub_year, subject_keywords, language, url_baca_online.
    """
    metadata = {
        'title': 'Tidak Diketahui',
        'author': 'Tidak Diketahui',
        'supervisor': '',
        'program_study': 'Tidak Diketahui',
        'faculty': '',
        'pub_year': None,
        'subject_keywords': '',
        'language': 'Indonesia',
        'url_baca_online': ''
    }

    tds = soup.find_all('td')
    for i in range(len(tds) - 1):
        label = tds[i].text.strip().lower()
        val = tds[i + 1].text.strip()

        if label == 'judul' and metadata['title'] == 'Tidak Diketahui':
            metadata['title'] = val
        elif label == 'pengarang' and metadata['author'] == 'Tidak Diketahui':
            metadata['author'] = val.replace('\n', ' ').strip()
        elif label == 'dosen pembimbing' and not metadata['supervisor']:
            metadata['supervisor'] = val.replace('\n', ' ').strip()
        elif label == 'program studi' and metadata['program_study'] == 'Tidak Diketahui':
            metadata['program_study'] = val
        elif label == 'fakultas' and not metadata['faculty']:
            metadata['faculty'] = val
        elif label == 'penerbitan' and not metadata['pub_year']:
            # Format: "Surabaya : Universitas Airlangga, 2025"
            import re
            year_match = re.search(r'\b(20\d{2})\b', val)
            if year_match:
                metadata['pub_year'] = int(year_match.group(1))
        elif label == 'subjek' and not metadata['subject_keywords']:
            metadata['subject_keywords'] = val.replace('\n', ', ').strip()
        elif label == 'bahasa' and metadata['language'] == 'Indonesia':
            metadata['language'] = val

    # Ambil URL tombol "Baca Online"
    baca_btn = soup.find('a', string=lambda t: t and 'Baca Online' in t)
    if baca_btn and baca_btn.get('href'):
        href = baca_btn.get('href')
        if href.startswith('http'):
            metadata['url_baca_online'] = href
        else:
            metadata['url_baca_online'] = f"https://ir.unair.ac.id/{href.lstrip('/')}"

    return metadata
```

### 2e. Tambahkan filter tahun 2025 di fungsi `process_document`

Setelah baris `meta = scrape_metadata(soup)`, tambahkan blok filter berikut:

```python
# FILTER: hanya proses dokumen terbitan tahun 2025
if meta['pub_year'] != 2025:
    print(f"--- SKIP (bukan 2025, tahun={meta['pub_year']}): {meta['title'][:40]} ---")
    return True  # return True agar tidak dianggap error, tapi tidak diproses
```

### 2f. Ganti blok INSERT ke database di fungsi `process_document`

Cari blok `INSERT INTO raw_documents` dan ganti seluruhnya dengan:

```python
cursor = db_conn.cursor()
insert_query = """
    INSERT INTO documents (
        title, author, supervisor, program_study, faculty,
        pub_year, subject_keywords, language,
        abstract_text, bab1_text,
        url_source, url_baca_online,
        ocr_status
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (url_source) DO NOTHING
"""
cursor.execute(insert_query, (
    meta['title'],
    meta['author'],
    meta['supervisor'],
    meta['program_study'],
    meta['faculty'],
    meta['pub_year'],
    meta['subject_keywords'],
    meta['language'],
    abstract_text,
    bab1_text,
    detail_url,
    meta['url_baca_online'],
    'done' if abstract_text else 'failed'
))
db_conn.commit()
cursor.close()
```

### 2g. Ganti blok penulisan CSV di fungsi `process_document`

Cari blok penulisan `csv.writer` dan ganti seluruhnya dengan:

```python
csv_file = 'data.csv'
file_exists = os.path.isfile(csv_file)
with open(csv_file, 'a', newline='', encoding='utf-8') as cb:
    writer = csv.writer(cb)
    if not file_exists:
        writer.writerow([
            'title', 'author', 'supervisor', 'program_study', 'faculty',
            'pub_year', 'subject_keywords', 'language',
            'abstract_text', 'bab1_text',
            'url_source', 'url_baca_online', 'ocr_status'
        ])
    writer.writerow([
        meta['title'],
        meta['author'],
        meta['supervisor'],
        meta['program_study'],
        meta['faculty'],
        meta['pub_year'],
        meta['subject_keywords'],
        meta['language'],
        abstract_text,
        bab1_text,
        detail_url,
        meta['url_baca_online'],
        'done' if abstract_text else 'failed'
    ])
```

### 2h. Hapus filter "Fakultas Vokasi" di `main_scraper` — scrape semua fakultas

Di fungsi `main_scraper`, ganti bagian yang mencari hanya Fakultas Vokasi dengan logika yang scrape semua fakultas:

```python
# Ganti bagian ini:
# vokasi_header = soup.find('h2', string=lambda t: t and 'Fakultas Vokasi' in t)
# ...
# prodi_table = vokasi_header.find_next_sibling('table')

# Dengan ini (scrape SEMUA prodi dari semua fakultas):
print("Mengambil semua program studi dari seluruh fakultas...")
prodi_links = []
for a in soup.find_all('a', class_='btn-primary'):
    href = a.get('href')
    if href and 'prodiId' in href:
        full_url = f"https://ir.unair.ac.id{href}" if href.startswith('/') else href
        if full_url not in prodi_links:
            prodi_links.append(full_url)

print(f"Total ditemukan {len(prodi_links)} program studi dari seluruh Unair.")
```

---

## TUGAS 3 — Reset `data.csv`

Hapus isi file `data.csv` (atau hapus filenya).
File baru akan otomatis dibuat saat scraper pertama kali berjalan
dengan header kolom yang sudah diperbarui.

---

## Ringkasan Perubahan

| File | Perubahan |
|---|---|
| `schema.sql` | Ganti seluruh isi dengan schema baru (tabel `documents`) |
| `scraper.py` | Nama tabel, metadata fields baru, filter tahun 2025, scrape semua fakultas |
| `data.csv` | Reset (hapus) — akan dibuat ulang otomatis |

## Yang TIDAK boleh diubah

- Logika OCR EasyOCR (fungsi `process_document` bagian loop halaman)
- Fungsi `extract_base_image_url`
- Fungsi `clear_temp_images`
- Fungsi `get_db_connection`
- File `auth.py`
- File `docker-compose.yml`
- File `.env.example`
