import requests
import os
import time
import urllib3
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load credentials from .env
load_dotenv()

CYBER_USERNAME = os.getenv("VPN_USERNAME") # NIM/NIP
CYBER_PASSWORD = os.getenv("VPN_PASSWORD")

# URL Portal IR Unair (Sesuaikan path URL jika berbeda - sesuai isu ini HTTP/HTTPS)
IR_BASE_URL = "https://ir.unair.ac.id/opac/"
LOGIN_URL = "https://ir.unair.ac.id/opac/site/loginanggota"

def check_vpn_connection():
    """
    Network Connectivity Check:
    Melakukan 'ping' ringan ke server IR untuk memastikan VPN menyala.
    """
    try:
        print(f"Mengecek konektivitas ke {IR_BASE_URL}...")
        # Gunakan timeout singkat untuk ping dan nonaktifkan verifikasi SSL
        response = requests.get(IR_BASE_URL, timeout=5, verify=False)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException:
        print("Peringatan: Pastikan VPN OpenVPN sudah menyala!")
        return False

def login_ir():
    """
    Automated Session Login:
    Menangani form login menggunakan requests.Session()
    Penting: Objek session yang dikembalikan tidak akan ditutup agar cookies tetap tersimpan.
    """
    if not check_vpn_connection():
        return None

    if not CYBER_USERNAME or not CYBER_PASSWORD:
        print("Error: VPN_USERNAME atau VPN_PASSWORD tidak ditemukan di file .env.")
        return None

    # Manajemen Sesi (Cookies) - Simpan objek ini
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': IR_BASE_URL,
        'X-Requested-With': 'XMLHttpRequest' # Header penting untuk AJAX Login InlisLite
    })

    try:
        print(f"Mencoba mengambil token CSRF dari halaman utama: {IR_BASE_URL}...")
        time.sleep(1) # Jeda keamanan
        
        response = session.get(IR_BASE_URL, timeout=10, verify=False)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        # InlisLite / Yii2 CSRF Token biasanya ada di tag meta
        csrf_param_meta = soup.find('meta', {'name': 'csrf-param'})
        csrf_token_meta = soup.find('meta', {'name': 'csrf-token'})
        
        csrf_param = csrf_param_meta['content'] if csrf_param_meta else '_csrf'
        csrf_token = csrf_token_meta['content'] if csrf_token_meta else ''

        payload = {
            'LoginKeanggotaanForm[noanggota]': CYBER_USERNAME,
            'LoginKeanggotaanForm[password]': CYBER_PASSWORD,
        }
        
        # Tambahkan token CSRF ke dalam payload Form menggunakan nama spesifik (_OpacInlislite)
        if csrf_token:
            payload[csrf_param] = csrf_token

        print("Mengirimkan data login ke server IR...")
        time.sleep(2)

        login_response = session.post(LOGIN_URL, data=payload, timeout=10, verify=False)
        login_response.raise_for_status()

        response_text_lower = login_response.text.lower()
        # Verifikasi jika server menolak password
        if "salah" in response_text_lower or "gagal" in response_text_lower or "failed" in response_text_lower:
            print("Status: GAGAL - NIM/Password salah atau login ditolak oleh server.")
            return None
        
        print("Status: SUKSES - Autentikasi berhasil. Sesi beserta cookies tersimpan.")
        return session

    except requests.exceptions.RequestException as e:
        print(f"Peringatan: Gagal login atau request terputus: {e}")
        return None
    except Exception as e:
        print(f"Terjadi error tidak terduga saat login: {e}")
        return None

if __name__ == "__main__":
    print("--- Test Modul Autentikasi IR Unair (Versi Manual VPN) ---")
    session = login_ir()
    
    if session:
        print("\nMelakukan tes akses ke halaman detail skripsi...")
        try:
            # Simulasi Akses Halaman Detail (misal: detail-opac?id=123)
            test_detail_url = f"{IR_BASE_URL}detail-opac?id=123" 
            test_response = session.get(test_detail_url, timeout=10, verify=False)
            
            # Verifikasi apakah halaman ter-load secara utuh dengan cookie yang valid
            if "Masuk" in test_response.text or "Login" in test_response.text:
                 print("Peringatan: Cookie mungkin tidak valid, sesi diminta login kembali.")
            else:
                 print(f"Sukses mengakses halaman detail! (Status: {test_response.status_code})")
                 
                 # Menerapkan logika Filter Fakultas Vokasi
                 if "Fakultas Vokasi" in test_response.text:
                     print("Filter: 'Fakultas Vokasi' terdeteksi. Memulai proses pengerukan metadata dan gambar folder /temporary/...")
                 else:
                     print("Filter: Bukan 'Fakultas Vokasi'. Dokumen dilewati (skip).")
                 
        except Exception as e:
            print(f"Gagal mengakses detail page: {e}")
    else:
         print("\nGagal membuat Session.")
 