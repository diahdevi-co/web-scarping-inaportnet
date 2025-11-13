import functions_framework
from selenium import webdriver
import pandas as pd
import time
from google.cloud import storage, bigquery
from datetime import datetime
import os
import configparser

from utils import get_detail_links, get_nomor_produk_list, scrape_detail_data

# Load configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")

config = configparser.ConfigParser()
if os.path.exists(CONFIG_PATH):
    config.read(CONFIG_PATH)
    BUCKET_NAME = config.get("gcp", "bucket_name", fallback="exampletesting999")
    BQ_PROJECT = config.get("gcp", "project_id", fallback="corporate-digital")
    BQ_DATASET = config.get("gcp", "dataset", fallback="DIGITAL_INTERSHIP")
    BQ_TABLE = config.get("gcp", "table", fallback="inaportnet_scraped_data")
else:
    print("Warning: config.ini not found, using default values.")
    BUCKET_NAME = "exampletesting999"
    BQ_PROJECT = "corporate-digital"
    BQ_DATASET = "DIGITAL_INTERSHIP"
    BQ_TABLE = "inaportnet_scraped_data"

# Selenium setup
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=options)
    return driver

# Upload to GCS
def upload_to_gcs_json(df: pd.DataFrame, bucket_name: str):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    blob_name = f"inaportnet/inaportnet_{timestamp}.json"

    blob = bucket.blob(blob_name)
    json_data = df.to_json(orient="records", indent=2, force_ascii=False)
    blob.upload_from_string(json_data, content_type="application/json")

    print(f"Uploaded to GCS: gs://{bucket_name}/{blob_name}")
    return f"gs://{bucket_name}/{blob_name}"

# Upload to BigQuery
def upload_to_bigquery(df: pd.DataFrame):
    client = bigquery.Client(project=BQ_PROJECT)
    table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND", autodetect=True)
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    print(f"Uploaded to BigQuery: {table_id}")

# Main scraping function
@functions_framework.http
def scrape_inaportnet(request):
    request_json = request.get_json(silent=True)
    base_url = request_json.get("base_url", "https://monitoring-inaportnet.dephub.go.id/monitoring")

    driver = setup_driver()
    all_data = []

    try:
        print(f"Starting scraping from {base_url}")
        links = get_detail_links(driver, base_url)

        for link in links:
            pkk_list = get_nomor_produk_list(driver, link)
            if pkk_list:
                result = scrape_detail_data(pkk_list)
                all_data.extend(result)

        if not all_data:
            return {"message": "No data found to scrape"}, 200

        df = pd.DataFrame(all_data)
        gcs_path = upload_to_gcs_json(df, BUCKET_NAME)
        upload_to_bigquery(df)

        return {
            "message": "Scraping and upload completed successfully",
            "rows_uploaded": len(df),
            "gcs_file": gcs_path
        }, 200

    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}, 500

    finally:
        driver.quit()

app = functions_framework.create_app('scrape_inaportnet')
