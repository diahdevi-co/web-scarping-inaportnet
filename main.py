import configparser
import pandas as pd
import json
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


def upload_json_to_gcs(bucket_name, blob_name, json_data):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(json.dumps(json_data, ensure_ascii=False, indent=2), content_type="application/json")
    print(f"Uploaded to GCS: gs://{bucket_name}/{blob_name}")
    return f"gs://{bucket_name}/{blob_name}"


def upload_to_bigquery(dataset_id, table_id, gcs_uri):
    client = bigquery.Client()
    table_ref = f"{client.project}.{dataset_id}.{table_id}"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    load_job = client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
    load_job.result()
    print(f"Loaded data to BigQuery: {table_ref}")


def main():
    # Membaca konfigurasi dari file .ini secara otomatis
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    default = config["DEFAULT"]
    ports_file = default["ports"]
    months = [m.strip() for m in default["months"].split(",")]
    years = [y.strip() for y in default["yr"].split(",")]
    source = default["source"].strip()
    source_code = default["source_code"].strip()
    base_url = default["pkk_url"].strip()

    bucket_name = default.get("gcs_bucket", "nama-bucket")
    dataset_id = default.get("bq_dataset", "nama_dataset")
    table_id = default.get("bq_table", "nama_tabel")

    # Siapkan WebDriver headless
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    ports_df = pd.read_csv(ports_file)
    all_data = []

    # Paralel scraping
    with ThreadPoolExecutor(max_workers=4) as executor:
        tasks = []
        for _, row in ports_df.iterrows():
            port_code = row.iloc[0].strip()
            for year in years:
                for month in months:
                    tasks.append(executor.submit(
                        process_port_month,
                        driver, port_code, year, month, base_url, source, source_code
                    ))

        for future in as_completed(tasks):
            result = future.result()
            if result:
                all_data.extend(result)

    driver.quit()

    if not all_data:
        print("Tidak ada data yang berhasil di-scrape.")
        return

    # Upload langsung ke GCS
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    blob_name = f"scraping_results/hasil_scraping_{timestamp}.json"
    gcs_uri = upload_json_to_gcs(bucket_name, blob_name, all_data)

    # Load ke BigQuery
    upload_to_bigquery(dataset_id, table_id, gcs_uri)

    print("\nProses selesai: Data berhasil diunggah langsung ke GCS dan BigQuery.")


if __name__ == "__main__":
    main()
