import os
import csv
import time
import requests
import psycopg2
import easyocr
import shutil
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Import auth yang sudah kita kerjakan di Issue #2
from auth import login_ir, IR_BASE_URL, check_vpn_connection

# Load kredensial
load_dotenv()

# Konfigurasi Database dari .env
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "skripsi_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Inisialisasi MESIN OCR (Memakai GPU VRAM RTX 3050)
print("Menginisialisasi model EasyOCR di mode GPU (CUDA)...")
ocr_reader = easyocr.Reader(['id', 'en'], gpu=True)

# Direktori sementara untuk menyimpan gambar halaman sebelum di-OCR
TMP_IMG_DIR = "temp_pages"
if not os.path.exists(TMP_IMG_DIR):
    os.makedirs(TMP_IMG_DIR)

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Error Database: {e}")
        return None

def get_existing_urls(db_conn):
    """Mengambil daftar URL dokumen yang sudah ada di database agar tidak di-scrape ulang."""
    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT url_source FROM documents")
        existing = {row[0] for row in cursor.fetchall()}
        cursor.close()
        return existing
    except Exception as e:
        print(f"Gagal mengambil riwayat dokumen: {e}")
        return set()

def clear_temp_images():
    """Menghapus gambar sementara setelah proses OCR selesai untuk 1 dokumen."""
    for f in os.listdir(TMP_IMG_DIR):
        os.remove(os.path.join(TMP_IMG_DIR, f))

def get_existing_doc_ids(db_conn):
    """Mengambil semua ID dokumen yang sudah ada di database untuk mencegah proses ulang OCR."""
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

def extract_base_image_url(soup):
    """
    Ekstrak form URL dasar menuju image dari Flip PDF link.
    """
    btn = soup.find(string=lambda t: t and 'Baca Online' in t)
    if btn:
        parent_a = btn.parent if btn.parent.name == 'a' else btn.parent.find('a')
        if not parent_a:
            parent_a = btn.find_parent('a')
            
        if parent_a and parent_a.get('href') and '../uploaded_files/temporary/' in parent_a.get('href'):
            href = parent_a.get('href')
            # href contoh: ../uploaded_files/temporary/DigitalCollection/XYZ/index.html
            base_dir = href.replace('../uploaded_files/', 'https://ir.unair.ac.id/uploaded_files/').replace('index.html', '')
            # Kita gunakan file kualitas mobile agar lebih ringan
            return f"{base_dir}files/mobile/"
            
    return None

def process_document(session, doc_id, db_conn, existing_urls):
    """Memproses 1 URL halaman dari pengunduhan sampai database."""
    detail_url = f"{IR_BASE_URL}detail-opac?id={doc_id}"
    
    if detail_url in existing_urls:
        print(f"\n--- SKIPPED: {doc_id} sudah ada di Database ---")
        return True
        
    print(f"\n--- Memproses Dokumen ID: {doc_id} ---")
    
    try:
        response = session.get(detail_url, timeout=15, verify=False)
        response.raise_for_status()
        html_text = response.text
        
        # Hapus filter teks Fakultas Vokasi karena sudah diambil dari index khusus Vokasi
        print("=> Mengekstrak metadata dari halaman dokumen...")
        soup = BeautifulSoup(html_text, 'html.parser')
        
        # 2. Ambil Metadata
        meta = scrape_metadata(soup)
        
        # FILTER: hanya proses dokumen terbitan tahun 2025
        if meta['pub_year'] != 2025:
            print(f"--- SKIP (bukan 2025, tahun={meta['pub_year']}): {meta['title'][:40]} ---")
            return True

        print(f"Judul: {meta['title'][:50]}...")
        
        # 3. Cari Base URL untuk Gambar
        base_img_url = extract_base_image_url(soup)
        if not base_img_url:
            print("=> Peringatan: Tautan PDF/Gambar asli tidak dapat ditemukan (kemungkinan terkunci).")
            # Tetap simpan metadata meski URL gambar gak ada.
            base_img_url = ""
        
        # 4. Targeted OCR: Pencarian Dinamis dengan Algoritma Pengenalan Pola Teks
        # Kita mem-parsing Halaman 1 per 1, dan akan langsung BERHENTI saat sistem mendeteksi teks "BAB 2" atau "BAB II" 
        # (sehingga tidak ada buang waktu OCR untuk sub bab yg tidak berguna).
        abstract_results = []
        bab1_results = []
        
        # Penanda state
        found_abstrak = False
        found_bab1 = False
        stop_ocr = False
        
        if base_img_url:
            for page_num in range(1, 16): # Target OCR: Halaman 1-15 sesuai instruksi
                if stop_ocr:
                    break
                    
                img_url = f"{base_img_url}{page_num}.jpg"
                img_path = os.path.join(TMP_IMG_DIR, f"page_{page_num}.jpg")
                
                print(f"  -> Mengunduh halaman {page_num} dari: {img_url}")
                
                try:
                    img_res = session.get(img_url, stream=True, verify=False, timeout=15)
                    if img_res.status_code == 200:
                        with open(img_path, 'wb') as f:
                            for chunk in img_res.iter_content(1024):
                                f.write(chunk)
                        
                        print(f"  -> OCR membaca halaman {page_num}...")
                        result = ocr_reader.readtext(img_path, detail=0)
                        cleansed_text = " ".join(result)
                        cleansed_upper = cleansed_text.upper()
                        
                        # ALGORITMA PENGENALAN POLA
                        
                        # 1. Hindari membaca halaman "Daftar Isi" yang sering mengandung kata Abstrak/Bab 1
                        if "............." in cleansed_text or "DAFTAR ISI" in cleansed_upper:
                            print("     [-] Ini daftar isi/tabel, dilewati.")
                            continue
                            
                        # 2. Deteksi BAB 2 (Prioritas Tertinggi: Stop Trigger)
                        # Menghentikan pencarian dokumen bila mencapai akhir Bab 1 / tinjauan pustaka
                        if "BAB II " in cleansed_upper or "BAB 2 " in cleansed_upper or "TINJAUAN PUSTAKA" in cleansed_upper:
                            print("     [!] Pola BAB 2 Terdeteksi. Menghentikan OCR dokumen ini (Selesai).")
                            stop_ocr = True
                            break # Hentikan unduh page PDF agar hemat performa
                            
                        # 3. Deteksi BAB 1 Pendahuluan (Format Roman atau Angka)
                        # Lebih spesifik agar tidak terpicu dengan sebatas kata "Pendahuluan" di Abstrak.
                        if "BAB I " in cleansed_upper or "BAB I" in cleansed_upper and "PENDAHULUAN" in cleansed_upper or "BAB 1 " in cleansed_upper:
                            if not found_bab1:
                                print("     [+] Pola BAB I (PENDAHULUAN) terdeteksi secara utuh!")
                            found_bab1 = True
                            found_abstrak = False # Hentikan pengisian abstrak saat masuk ke zona Bab 1
                            
                        # 4. Deteksi Lembar Abstrak
                        elif "ABSTRAK" in cleansed_upper or "ABSTRACT" in cleansed_upper:
                            if not found_bab1: # Hanya mulai abstrak jika memang bab 1 belum dideteksi
                                if not found_abstrak:
                                    print("     [+] Pola ABSTRAK terdeteksi!")
                                found_abstrak = True
                                
                        # Logika Penyimpanan Teks
                        if found_bab1:
                            bab1_results.append(cleansed_text)
                        elif found_abstrak:
                            abstract_results.append(cleansed_text)
                            
                    else:
                        print(f"  -> Batas halaman akhir PDF tercapai (Status {img_res.status_code})")
                        break 
                except Exception as read_err:
                    print(f"  -> Kesalahan pada halaman {page_num}: {read_err}")
                
                time.sleep(1)
        
        abstract_text = " ".join(abstract_results)
        bab1_text = " ".join(bab1_results)
        
        # 5. Database Storage (PostgreSQL dg flag Vokasi)
        print("=> Menyimpan ke Database PostgreSQL dan CSV...")
        
        # Insert DB
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
        
        # Insert CSV
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
            
        print("=> SUKSES: Data tersimpan di Database dan `data.csv`.")
        clear_temp_images()
        return True

    except Exception as e:
        print(f"=> ERROR saat memproses {doc_id}: {e}")
        return False

def main_scraper():
    print("=== Menjalankan Mesin Scraping (Mode SEMUA Fakultas - Mode GPU/CUDA) ===")
    
    db_conn = get_db_connection()
    if not db_conn: return
    
    existing_urls = get_existing_urls(db_conn)

    existing_ids = get_existing_doc_ids(db_conn)
    print(f"=> Info: Ditemukan {len(existing_ids)} dokumen di Database. Akan dilewati agar efisien.")

    # Otentikasi
    session = login_ir()
    if not session:
        print("Proses dihentikan karena gagal Login.")
        db_conn.close()
        return
        
    print("\nMengambil direktori seluruh fakultas...")
    index_url = "https://ir.unair.ac.id/opac/browsev2/view-faculty-indexing"
    res = session.get(index_url, verify=False)
    soup = BeautifulSoup(res.text, 'html.parser')
    
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
    
    # Mode Pencarian Mendalam ke Seluruh Prodi & Seluruh Dokumen yang Tampil
    for prodi_url in prodi_links:
        print(f"\n=== MENGAMBIL DAFTAR DOKUMEN DARI PRODI: {prodi_url} ===")
        try:
            res_prodi = session.get(prodi_url, verify=False)
            prodi_soup = BeautifulSoup(res_prodi.text, 'html.parser')
            
            doc_ids = []
            for a in prodi_soup.find_all('a'):
                href = a.get('href')
                if href and 'detail-opac?id=' in href:
                    doc_id = href.split('id=')[-1]
                    if doc_id not in doc_ids: # Hindari id duplikat di halaman yang sama
                        doc_ids.append(doc_id)
            
            print(f"Ditemukan {len(doc_ids)} dokumen unik di halaman prodi ini.")
            
            # Iterasi mengunduh seluruh dokumen di halaman terkait
            for idx, doc_id in enumerate(doc_ids, start=1):
                if doc_id in existing_ids:
                    print(f"--- [Prodi: {prodi_url.split('prodiId=')[-1]}] SKIP {idx}/{len(doc_ids)}: ID {doc_id[:8]}... sudah tersimpan ---")
                    continue
                    
                print(f"--- [Prodi: {prodi_url.split('=')[-1]}] Memproses {idx}/{len(doc_ids)} ---")
                is_success = process_document(session, doc_id, db_conn, existing_urls)
                if is_success:
                    existing_ids.add(doc_id)
                time.sleep(3) # Delay anti-banned
        except Exception as e:
            print(f"Gagal memproses prodi {prodi_url}: {e}")
            
    db_conn.close()
    print("\n=== Selesai! ===")

if __name__ == "__main__":
    main_scraper()
