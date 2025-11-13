import os
import time
import random
import requests
from bs4 import BeautifulSoup
from lxml import etree
from tqdm import tqdm
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Fungsi HTTP dengan retry otomatis
def get_with_retry(url, max_retries=5, timeout=30, delay=10):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            print(f"Percobaan {attempt+1}/{max_retries} gagal: Timeout.")
        except requests.exceptions.ConnectionError as e:
            print(f"Percobaan {attempt+1}/{max_retries} gagal: Koneksi error: {e}")
        except requests.exceptions.RequestException as e:
            print(f"Percobaan {attempt+1}/{max_retries} gagal: {e}")

        time.sleep(delay + random.uniform(1, 3))

    print(f"Gagal mengakses {url} setelah {max_retries} percobaan.")
    return None


# Ambil semua link detail dari halaman utama
def get_detail_links(driver, url):
    print(f"Memuat halaman utama: {url}")
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.dataLayanan"))
        )
    except Exception as e:
        print(f"Timeout: Tidak menemukan elemen 'a.dataLayanan' ({type(e).__name__})")
        return []

    links = [
        el.get_attribute("data-url")
        for el in driver.find_elements(By.CSS_SELECTOR, "a.dataLayanan")
        if el.get_attribute("data-url")
    ]
    print(f"Ditemukan {len(links)} link detail.")
    return links


# Ambil daftar nomor PKK dari modal AJAX
def get_nomor_produk_list(driver, url):
    print(f"Membuka modal AJAX: {url}")
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
        )
    except Exception as e:
        print(f"Timeout: Modal tidak muncul atau tabel kosong ({type(e).__name__})")
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")
    nomor_produk = [
        row.find_all("td")[1].get_text(strip=True)
        for row in soup.select("table tbody tr")
        if len(row.find_all("td")) >= 2
    ]
    print(f"Ditemukan {len(nomor_produk)} nomor produk.")
    return nomor_produk


# Scraping halaman detail setiap PKK
def scrape_detail_data(pkk_list):
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

            # HEADER UTAMA
            header = soup.select_one("div.card-header h6.card-title b")
            header_text = header.get_text(strip=True) if header else ""
            kode_pkk, nama_kapal, tipe_kapal = "", "", ""

            if " - " in header_text:
                parts = header_text.split(" - ", 1)
                kode_pkk = parts[0].strip()
                kapal_info_text = parts[1].strip()
                if "(" in kapal_info_text:
                    nama_kapal = kapal_info_text.split("(")[0].strip()
                    tipe_kapal = kapal_info_text.split("(")[-1].replace(")", "").strip()
                else:
                    nama_kapal = kapal_info_text.strip()

            nakhoda = soup.select_one("div.card-header .badge.bg-blue")
            nakhoda_text = (
                nakhoda.get_text(strip=True).replace("NAKHODA :", "").strip()
                if nakhoda else ""
            )

            # INFORMASI KAPAL DAN KEAGENAN
            kapal_info = {
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
                table = kapal_div.find_parent("div", class_="card-body").find("table")
                for row in table.select("tbody tr"):
                    cols = [c.get_text(" ", strip=True) for c in row.select("td")]
                    if len(cols) >= 6:
                        kiri_label, kiri_val = cols[0].strip(), cols[2].strip()
                        kanan_label, kanan_val = cols[3].strip(), cols[5].strip()
                        if kiri_label in kapal_info:
                            kapal_info[kiri_label] = kiri_val
                        if kanan_label in kapal_info:
                            kapal_info[kanan_label] = kanan_val

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
                table = trayek_div.find_parent("div", class_="card-body").find("table")
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

            hasil.append({
                "Nomor PKK": kode_pkk or ids,
                "Nama Kapal": nama_kapal,
                "Tipe Kapal": tipe_kapal,
                "Nakhoda": nakhoda_text,
                **kapal_info,
                **trayek_info
            })

            time.sleep(random.uniform(1.2, 2.5))

        except Exception as e:
            print(f"Error saat scraping {ids}: {type(e).__name__} - {e}")

    return hasil
