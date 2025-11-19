import os
import time
import random
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup
from lxml import etree
from tqdm import tqdm
from datetime import date, datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def get_with_retry(url, max_retries=5, timeout=30, initial_delay=5):
    """
    HTTP request dengan retry mechanism.
    Menangani kode 429 (Too Many Requests) dengan Exponential Backoff.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            
            # --- Penanganan Khusus untuk HTTP 429 (Rate Limit) ---
            if response.status_code == 429:
                # Terapkan Exponential Backoff
                wait_time = initial_delay * (2 ** attempt) + random.uniform(1, 3)
                print(f"Percobaan {attempt+1}/{max_retries} gagal: Ditolak (HTTP 429 - Rate Limit). Menunggu {wait_time:.2f} detik.")
                time.sleep(wait_time)
                continue  # Lanjutkan ke percobaan berikutnya
            
            # Raise exception untuk kode status 4xx/5xx lainnya
            response.raise_for_status() 
            return response
            
        except requests.exceptions.Timeout:
            print(f"Percobaan {attempt+1}/{max_retries} gagal: Timeout ({timeout}s).")
        except requests.exceptions.ConnectionError as e:
            print(f"Percobaan {attempt+1}/{max_retries} gagal: Koneksi error: {e}")
        except requests.exceptions.RequestException as e:
            # Ini menangani 4xx/5xx selain 429
            print(f"Percobaan {attempt+1}/{max_retries} gagal: {e}")

        # Jeda standar untuk kegagalan koneksi/timeout
        time.sleep(initial_delay + random.uniform(1, 3))

    print(f"Gagal mengakses {url} setelah {max_retries} percobaan.")
    return None


def get_detail_links(driver, url):
    """Ambil semua link detail dari halaman utama"""
    print(f"Memuat halaman utama: {url}")
    driver.get(url)
    
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.dataLayanan"))
        )
    except Exception as e:
        print(f"Timeout: Tidak menemukan elemen 'a.dataLayanan' - {type(e).__name__}")
        return []

    links = [
        el.get_attribute("data-url")
        for el in driver.find_elements(By.CSS_SELECTOR, "a.dataLayanan")
        if el.get_attribute("data-url")
    ]
    print(f"Ditemukan {len(links)} link detail.")
    return links


def get_nomor_produk_list(driver, url):
    """Ambil daftar nomor PKK dari modal AJAX"""
    print(f"Membuka modal AJAX: {url}")
    driver.get(url)
    
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
        )
    except Exception as e:
        print(f"Timeout: Modal tidak muncul atau tabel kosong - {type(e).__name__}")
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")
    nomor_produk = [
        row.find_all("td")[1].get_text(strip=True)
        for row in soup.select("table tbody tr")
        if len(row.find_all("td")) >= 2
    ]
    print(f"Ditemukan {len(nomor_produk)} nomor produk.")
    return nomor_produk


def scrape_detail_data(pkk_list):
    """
    Scraping detail data untuk setiap PKK
    Jeda ditingkatkan menjadi 5.0 - 10.0 detik untuk menghindari Rate Limit (429).
    Returns: List of dictionaries (JSON-ready format)
    """
    base_detail = "https://monitoring-inaportnet.dephub.go.id/monitoring/detail?nomor_pkk="
    hasil = []

    for ids in tqdm(pkk_list, desc="Scraping detail PKK"):
        url = base_detail + ids
        response = get_with_retry(url)
        if not response:
            print(f"Lewati {ids} karena gagal diakses.")
            continue

        try:
            soup = BeautifulSoup(response.content, "html.parser")

            # HEADER
            header = soup.select_one("div.card-header h6.card-title b")
            header_text = header.get_text(strip=True) if header else ""
            kode_pkk, nama_kapal, tipe_kapal = "", "", ""

            if " - " in header_text:
                parts = header_text.split(" - ", 1)
                kode_pkk = parts[0].strip()
                kapal_info = parts[1].strip()
                if "(" in kapal_info:
                    nama_kapal = kapal_info.split("(")[0].strip()
                    tipe_kapal = kapal_info.split("(")[-1].replace(")", "").strip()
                else:
                    nama_kapal = kapal_info.strip()

            nakhoda = soup.select_one("div.card-header .badge.bg-blue")
            nakhoda_text = (
                nakhoda.get_text(strip=True).replace("NAKHODA :", "").strip()
                if nakhoda else ""
            )

            # INFORMASI KAPAL DAN KEAGENAN
            kapal_info_dict = {
                "Nama Perusahaan": "",
                "Bendera / Call Sign / IMO": "",
                "Tanda Pendaftaran Kapal": "",
                "GT / DWT": "",
                "Draft Depan / Belakang / Max": "",
                "Panjang / Lebar": "",
                "AAIC": ""
            }

            kapal_div = soup.find("b", string=lambda x: x and "INFORMASI KAPAL DAN KEAGENAN" in x)
            if kapal_div:
                table = kapal_div.find_parent("div", class_="card-body")
                if table:
                    table = table.find("table")
                    if table:
                        for row in table.select("tbody tr"):
                            cols = [c.get_text(" ", strip=True) for c in row.select("td")]
                            if len(cols) >= 6:
                                kiri_label, kiri_val = cols[0].strip(), cols[2].strip()
                                kanan_label, kanan_val = cols[3].strip(), cols[5].strip()
                                if kiri_label in kapal_info_dict:
                                    kapal_info_dict[kiri_label] = kiri_val
                                if kanan_label in kapal_info_dict:
                                    kapal_info_dict[kanan_label] = kanan_val

            # INFORMASI KEDATANGAN DAN KEBERANGKATAN
            trayek_info = {
                "Jenis Trayek (Kedatangan)": "",
                "Nomor Trayek (Kedatangan)": "",
                "ETA": "",
                "Sebelum Asal": "",
                "Asal": "",
                "No. SSM (Kedatangan)": "",
                "Single Billing (Kedatangan)": "",
                "Jenis Trayek (Keberangkatan)": "",
                "Nomor Trayek (Keberangkatan)": "",
                "ETD": "",
                "Singgah": "",
                "Tujuan": "",
                "No. SSM (Keberangkatan)": "",
                "Single Billing (Keberangkatan)": ""
            }

            trayek_div = soup.find("b", string=lambda x: x and "INFORMASI KEDATANGAN DAN KEBERANGKATAN" in x)
            if trayek_div:
                table = trayek_div.find_parent("div", class_="card-body")
                if table:
                    table = table.find("table")
                    if table:
                        for row in table.select("tbody tr"):
                            cols = [c.get_text(" ", strip=True) for c in row.select("td")]
                            if len(cols) >= 6:
                                kiri_label, kiri_val = cols[0].strip(), cols[2].strip()
                                kanan_label, kanan_val = cols[3].strip(), cols[5].strip()

                                if kiri_label and f"{kiri_label} (Kedatangan)" in trayek_info:
                                    trayek_info[f"{kiri_label} (Kedatangan)"] = kiri_val
                                elif kiri_label in trayek_info:
                                    trayek_info[kiri_label] = kiri_val

                                if kanan_label and f"{kanan_label} (Keberangkatan)" in trayek_info:
                                    trayek_info[f"{kanan_label} (Keberangkatan)"] = kanan_val
                                elif kanan_label in trayek_info:
                                    trayek_info[kanan_label] = kanan_val

            # SIMPAN KE DICTIONARY (Format JSON-ready dengan snake_case)
            record = {
                "nomor_pkk": kode_pkk or ids,
                "nama_kapal": nama_kapal,
                "tipe_kapal": tipe_kapal,
                "nakhoda": nakhoda_text,
                "nama_perusahaan": kapal_info_dict.get("Nama Perusahaan", ""),
                "bendera_callsign_imo": kapal_info_dict.get("Bendera / Call Sign / IMO", ""),
                "tanda_pendaftaran_kapal": kapal_info_dict.get("Tanda Pendaftaran Kapal", ""),
                "gt_dwt": kapal_info_dict.get("GT / DWT", ""),
                "draft_depan_belakang_max": kapal_info_dict.get("Draft Depan / Belakang / Max", ""),
                "panjang_lebar": kapal_info_dict.get("Panjang / Lebar", ""),
                "aaic": kapal_info_dict.get("AAIC", ""),
                "jenis_trayek_kedatangan": trayek_info.get("Jenis Trayek (Kedatangan)", ""),
                "nomor_trayek_kedatangan": trayek_info.get("Nomor Trayek (Kedatangan)", ""),
                "eta": trayek_info.get("ETA", ""),
                "sebelum_asal": trayek_info.get("Sebelum Asal", ""),
                "asal": trayek_info.get("Asal", ""),
                "no_ssm_kedatangan": trayek_info.get("No. SSM (Kedatangan)", ""),
                "single_billing_kedatangan": trayek_info.get("Single Billing (Kedatangan)", ""),
                "jenis_trayek_keberangkatan": trayek_info.get("Jenis Trayek (Keberangkatan)", ""),
                "nomor_trayek_keberangkatan": trayek_info.get("Nomor Trayek (Keberangkatan)", ""),
                "etd": trayek_info.get("ETD", ""),
                "singgah": trayek_info.get("Singgah", ""),
                "tujuan": trayek_info.get("Tujuan", ""),
                "no_ssm_keberangkatan": trayek_info.get("No. SSM (Keberangkatan)", ""),
                "single_billing_keberangkatan": trayek_info.get("Single Billing (Keberangkatan)", ""),
                "scraped_at": datetime.now().isoformat()
            }
            
            hasil.append(record)
            
            # --- Jeda Regulernya Diperpanjang ---
            # Mengurangi frekuensi permintaan untuk menghindari rate limiting 429
            time.sleep(random.uniform(5.0, 10.0))

        except Exception as e:
            print(f"Error saat scraping {ids}: {type(e).__name__} - {e}")
            continue

    return hasil


def export_to_json(data, path):
    """Simpan hasil scraping ke file JSON lokal"""
    if not data:
        print("Data kosong, tidak disimpan.")
        return

    if not path.lower().endswith(".json"):
        path += ".json"

    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Data berhasil disimpan ke {path}")
        print(f"Total records: {len(data)}")
    except Exception as e:
        print(f"Error menyimpan JSON: {type(e).__name__} - {e}")