import functions_framework
import os
import json
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from google.cloud import storage, bigquery
from utils import (
    get_detail_links,
    get_nomor_produk_list,
    scrape_detail_data
)

# Konfigurasi environment
BUCKET_NAME = os.getenv("GCS_BUCKET", "nama-bucket")
BQ_PROJECT = os.getenv("BQ_PROJECT", "nama-project")
BQ_DATASET = os.getenv("BQ_DATASET", "nama_dataset")
BQ_TABLE = os.getenv("BQ_TABLE", "nama_tabel")

PORTS_FILE = os.getenv("PORTS_FILE", "ports.csv")
MONTHS = os.getenv("MONTHS", "01,02,03,04,05,06").split(",")
YEARS = os.getenv("YEARS", "2024,2025").split(",")
SOURCE = os.getenv("SOURCE", "service-code")
SOURCE_CODE = os.getenv("SOURCE_CODE", "SL001")
BASE_URL = os.getenv("PKK_URL", "https://monitoring-inaportnet.dephub.go.id/monitoring/detail-pelabuhan")



# Setup ChromeDriver
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


# Fungsi scraping per pelabuhan

def process_port_month(driver, port_code, year, month, base_url, source, source_code):
    url_list = f"{base_url}/{port_code}/{source}/{source_code}/{year}/{month}"
    print(f"\nMemproses {port_code} - {year}/{month}")

    try:
        modal_links = get_detail_links(driver, url_list)
        nomor_pkk_all = []

        for modal_url in modal_links:
            nomor_pkk = get_nomor_produk_list(driver, modal_url)
            nomor_pkk_all.extend([p for p in nomor_pkk if ".DN." in p])

        if nomor_pkk_all:
            data = scrape_detail_data(nomor_pkk_all)
            return data
        else:
            print(f"Tidak ada PKK DN untuk {port_code}-{month}/{year}")
            return []
    except Exception as e:
        print(f"Gagal memproses {url_list}: {type(e).__name__} - {e}")
        return []



# Upload ke GCS dan BigQuery

def upload_json_to_gcs(bucket_name, blob_name, json_data):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(json.dumps(json_data, ensure_ascii=False, indent=2), content_type="application/json")
    print(f"Uploaded to GCS: gs://{bucket_name}/{blob_name}")
    return f"gs://{bucket_name}/{blob_name}"


def upload_to_bigquery(dataset_id, table_id, gcs_uri, project_id=None):
    client = bigquery.Client(project=project_id)
    table_ref = f"{client.project}.{dataset_id}.{table_id}"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    load_job = client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
    load_job.result()
    print(f"Loaded data to BigQuery: {table_ref}")



# Fungsi utama Cloud Function
@functions_framework.http
def scrape_inaportnet(request):
    driver = setup_driver()
    all_data = []

    try:
        ports_df = pd.read_csv(PORTS_FILE)

        # Jalankan scraping paralel
        with ThreadPoolExecutor(max_workers=4) as executor:
            tasks = []
            for _, row in ports_df.iterrows():
                port_code = row.iloc[0].strip()
                for year in YEARS:
                    for month in MONTHS:
                        tasks.append(executor.submit(
                            process_port_month,
                            driver, port_code, year, month, BASE_URL, SOURCE, SOURCE_CODE
                        ))

            for future in as_completed(tasks):
                result = future.result()
                if result:
                    all_data.extend(result)

        if not all_data:
            print("Tidak ada data yang berhasil di-scrape.")
            return {"message": "Tidak ada data yang ditemukan"}, 200

        # Upload ke GCS
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_name = f"scraping_results/hasil_scraping_{timestamp}.json"
        gcs_uri = upload_json_to_gcs(BUCKET_NAME, blob_name, all_data)

        # Upload ke BigQuery
        upload_to_bigquery(BQ_DATASET, BQ_TABLE, gcs_uri, project_id=BQ_PROJECT)

        return {
            "message": "Scraping dan upload berhasil",
            "gcs_file": gcs_uri,
            "rows_uploaded": len(all_data)
        }, 200

    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
        return {"error": str(e)}, 500

    finally:
        driver.quit()



# Untuk Gunicorn (Cloud Run)
app = functions_framework.create_app('scrape_inaportnet', 'main.py')
