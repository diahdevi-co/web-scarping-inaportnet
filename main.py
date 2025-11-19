import functions_framework
from selenium import webdriver
import pandas as pd
import time
import json
from google.cloud import storage, bigquery
from datetime import datetime
import os
import configparser

# Import fungsi dari utils.py
from utils import (
    get_detail_links,
    get_nomor_produk_list,
    scrape_detail_data
)

# Load configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")
config = configparser.ConfigParser()

try:
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
        print("config.ini loaded successfully")
    else:
        print("WARNING: config.ini not found, using defaults")
        config['gcp'] = {
            'bucket_name': 'exampletesting9999',
            'project_id': 'corporate-digital',
            'dataset': 'DIGITAL_INTERNSHIP',
            'table': 'inaportnet_scraped_data'
        }
        config['DEFAULT'] = {
            'ports': 'ports.csv',
            'months': '01,02,03,04,05,06,07,08,09,10,11,12',
            'yr': '2025',
            'source': 'service-code',
            'source_code': 'SL001',
            'pkk_url': 'https://monitoring-inaportnet.dephub.go.id/monitoring/detail-pelabuhan'
        }
except Exception as e:
    print(f"Error loading config: {e}")

BUCKET_NAME = config.get("gcp", "bucket_name", fallback="exampletesting9999")
BQ_PROJECT = config.get("gcp", "project_id", fallback="corporate-digital")
BQ_DATASET = config.get("gcp", "dataset", fallback="DIGITAL_INTERNSHIP")
BQ_TABLE = config.get("gcp", "table", fallback="inaportnet_scraped_data")

print(f"Config: Bucket={BUCKET_NAME}, Project={BQ_PROJECT}")


def setup_driver():
    """Setup Chrome driver"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    
    try:
        driver = webdriver.Chrome(options=options)
        print("Chrome driver initialized successfully")
        return driver
    except Exception as e:
        print(f"Chrome driver initialization failed: {e}")
        raise


def upload_to_gcs_json(data_list: list, bucket_name: str):
    """
    Upload list of dictionaries ke GCS sebagai JSON
    Input dari utils.scrape_detail_data() sudah dalam format JSON-ready
    """
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_name = f"inaportnet/inaportnet_{timestamp}.json"
        blob = bucket.blob(blob_name)
        
        # Convert list to JSON string
        json_data = json.dumps(data_list, indent=2, ensure_ascii=False)
        
        # Upload to GCS
        blob.upload_from_string(json_data, content_type="application/json")
        
        gcs_path = f"gs://{bucket_name}/{blob_name}"
        print(f"Successfully uploaded to GCS: {gcs_path}")
        print(f"  Total records: {len(data_list)}")
        print(f"  File size: {len(json_data)} bytes")
        
        return gcs_path
    except Exception as e:
        print(f"GCS upload failed: {e}")
        raise


def upload_to_bigquery_json(data_list: list):
    """
    Upload list of dictionaries ke BigQuery
    Input dari utils.scrape_detail_data() sudah dalam format JSON-ready
    """
    try:
        client = bigquery.Client(project=BQ_PROJECT)
        table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
        
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition="WRITE_APPEND",
            autodetect=True,
        )
        
        # BigQuery client dapat handle list of dicts langsung
        job = client.load_table_from_json(
            data_list,
            table_id,
            job_config=job_config
        )
        
        job.result()  # Wait for completion
        
        table = client.get_table(table_id)
        print(f"Successfully uploaded to BigQuery: {table_id}")
        print(f"  Rows inserted: {len(data_list)}")
        print(f"  Total rows in table: {table.num_rows}")
        
    except Exception as e:
        print(f"BigQuery upload failed: {e}")
        raise


def process_port_month(driver, port_code, year, month, base_url, source, source_code):
    """Process scraping untuk satu port dan bulan"""
    url_list = f"{base_url}/{port_code}/{source}/{source_code}/{year}/{month}"
    print(f"\nMemproses {port_code} - {year}/{month}")
    
    try:
        # Gunakan fungsi dari utils.py
        modal_links = get_detail_links(driver, url_list)
        nomor_pkk_all = []
        
        for modal_url in modal_links:
            # Gunakan fungsi dari utils.py
            nomor_pkk = get_nomor_produk_list(driver, modal_url)
            # Filter hanya PKK DN
            nomor_pkk_all.extend([p for p in nomor_pkk if ".DN." in p])
        
        if nomor_pkk_all:
            print(f"Ditemukan {len(nomor_pkk_all)} PKK DN untuk {port_code}-{month}/{year}")
            # Gunakan fungsi dari utils.py - returns JSON-ready list
            data = scrape_detail_data(nomor_pkk_all)
            return data
        else:
            print(f"Tidak ada PKK DN untuk {port_code}-{month}/{year}")
            return []
            
    except Exception as e:
        print(f"Gagal memproses {url_list}: {type(e).__name__} - {e}")
        return []


@functions_framework.http
def scrape_inaportnet(request):
    """
    HTTP Cloud Function untuk scraping Inaportnet
    GET / -> health check
    POST / -> trigger scraping
    """
    
    # Handle CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    # Health check
    if request.method == 'GET':
        print("Health check request received")
        return ({
            "status": "healthy",
            "service": "inaportnet-scraper",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "message": "Service is running. Use POST method to trigger scraping."
        }, 200, headers)
    
    # Only POST triggers scraping
    if request.method != 'POST':
        return ({
            "status": "error",
            "message": "Method not allowed. Use POST to trigger scraping.",
            "timestamp": datetime.now().isoformat()
        }, 405, headers)
    
    driver = None
    
    try:
        print("="*60)
        print("Starting scraping process...")
        print("="*60)
        
        # Parse request
        request_json = request.get_json(silent=True)
        
        # Config
        ports_file = config.get("DEFAULT", "ports", fallback="ports.csv")
        months = config.get("DEFAULT", "months", fallback="01,02,03,04,05,06,07,08,09,10,11,12").split(",")
        year = config.get("DEFAULT", "yr", fallback="2025")
        source = config.get("DEFAULT", "source", fallback="service-code")
        source_code = config.get("DEFAULT", "source_code", fallback="SL001")
        base_url = config.get("DEFAULT", "pkk_url", fallback="https://monitoring-inaportnet.dephub.go.id/monitoring/detail-pelabuhan")
        
        # Override from request
        if request_json:
            year = request_json.get("year", year)
            months = request_json.get("months", months)
            if isinstance(months, str):
                months = [m.strip() for m in months.split(",")]
        
        print(f"Configuration: year={year}, months={months}")
        
        # Initialize driver
        print("\n[1/3] Initializing Chrome driver...")
        driver = setup_driver()
        
        # Load ports
        print("\n[2/3] Loading ports data...")
        if os.path.exists(ports_file):
            ports_df = pd.read_csv(ports_file)
            print(f"Loaded {len(ports_df)} ports from {ports_file}")
        else:
            print(f"WARNING: {ports_file} not found, using default ports")
            ports_df = pd.DataFrame({
                'PORT_ID': ['IDBDJ', 'IDJKT', 'IDSRG'],
                'PORTS': ['BANJARMASIN', 'JAKARTA', 'SEMARANG']
            })
        
        # Scraping process
        all_data = []
        
        print(f"\n[3/3] Processing {len(ports_df)} ports for {len(months)} months...")
        
        for idx, row in ports_df.iterrows():
            port_code = row.iloc[0].strip()
            port_name = row.iloc[1].strip() if len(row) > 1 else port_code
            
            print(f"\n--- Processing Port: {port_name} ({port_code}) ---")
            
            for month in months:
                month = month.strip()
                try:
                    # Data sudah dalam format JSON-ready dari utils.py
                    result = process_port_month(
                        driver, port_code, year, month, 
                        base_url, source, source_code
                    )
                    if result:
                        all_data.extend(result)
                        print(f"  Collected {len(result)} records from {port_code}-{month}")
                except Exception as e:
                    print(f"  Error processing {port_code}-{month}: {e}")
                    continue
                
                time.sleep(2)
        
        if not all_data:
            return ({
                "status": "warning",
                "message": "No data scraped from any ports",
                "ports_processed": len(ports_df),
                "months_processed": len(months),
                "timestamp": datetime.now().isoformat()
            }, 200, headers)
        
        print(f"\n[4/4] Uploading {len(all_data)} records...")
        
        # Upload - data sudah JSON-ready dari utils.py
        gcs_path = upload_to_gcs_json(all_data, BUCKET_NAME)
        upload_to_bigquery_json(all_data)
        
        print("\n" + "="*60)
        print("SCRAPING COMPLETED SUCCESSFULLY")
        print("="*60)
        
        return ({
            "status": "success",
            "message": "Scraping and upload completed successfully",
            "rows_uploaded": len(all_data),
            "ports_processed": len(ports_df),
            "months_processed": len(months),
            "gcs_file": gcs_path,
            "bigquery_table": f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}",
            "data_format": "JSON",
            "timestamp": datetime.now().isoformat()
        }, 200, headers)
        
    except Exception as e:
        print("\n" + "="*60)
        print("ERROR OCCURRED")
        print("="*60)
        print(f"Error: {str(e)}")
        
        import traceback
        traceback.print_exc()
        
        return ({
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": datetime.now().isoformat()
        }, 500, headers)
        
