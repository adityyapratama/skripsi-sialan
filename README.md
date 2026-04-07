# Repository Skripsi Unair Scraper & Processor

Automated pipeline for collecting metadata and processing thesis documents from Airlangga University repository.

## 🚀 Setup Instructions (Issue #1 Resolution)

1.  **Python Environment**:
    ```powershell
    python -m venv venv
    .\venv\Scripts\activate
    pip install -r requirements.txt
    ```

2.  **Kredensial VPN & SSO**:
    - Salin file `.env.example` menjadi `.env`.
    - Isi `VPN_USERNAME` dan `VPN_PASSWORD` dengan akun Cyber Unair kamu.
    - **OpenVPN CLI**: `openvpn --config <file.ovpn> --auth-user-pass credentials.txt`.
    - Pastikan **OpenVPN** sudah terinstall untuk mengakses domain internal kampus (`ir.unair.ac.id`).

3.  **Database Setup (Docker RECOMMENDED)**:
    - Pastikan **Docker Desktop** sudah berjalan.
    - Jalankan perintah: `docker-compose up -d`.
    - Database akan otomatis membuat tabel dan mengaktifkan `pgvector` sesuai isi `schema.sql`.

4.  **Menjalankan Autentikasi**:
    - Jalankan `python auth.py` untuk mengetes login session setelah VPN aktif.

## ⚙️ Development Guidelines

- **Rate Limiting**: Gunakan jeda random antara request (misal 3-7 detik) agar tidak di-banned.
- **Resource Management**: Scraping untuk OCR (EasyOCR/Tesseract) hanya dilakukan pada halaman 1-15 per dokumen (RTX 3050 friendly).
- **Security**: Jangan pernah membagikan file `.env` atau commit file tersebut ke repositori publik.

---
**Status Proyek**: Environment Setup Complete (Issue #1).
