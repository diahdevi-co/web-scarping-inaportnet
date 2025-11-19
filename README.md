# Inaportnet Scraper
Proyek ini adalah scraper untuk data Inaportnet yang dibungkus sebagai Google Cloud Function. Hasil scraping disimpan ke Google Cloud Storage (GCS) dan diunggah ke BigQuery.

Persyaratan
- Python 3.10+
- dependencies: lihat [requirements.txt](requirements.txt)
- Google Cloud SDK (untuk deploy) atau akses service account dengan permission ke GCS & BigQuery
- Chromedriver / headless Chrome (pakai container atau environment yang sudah terpasang)

-----------
Utama dikendalikan melalui [config.ini](config.ini). Nilai penting:
- gcp.bucket_name — bucket GCS target
- gcp.project_id — project BigQuery
- gcp.dataset — dataset BigQuery
- gcp.table — tabel BigQuery
- DEFAULT.ports — path ke [ports.csv](ports.csv)
- DEFAULT.months, DEFAULT.yr, DEFAULT.source, DEFAULT.source_code

Cara kerja (ringkas)
1. Entry point: [`main.scrape_inaportnet`](main.py) — menerima POST untuk memicu scraping.
2. Inisialisasi driver Chrome: [`main.setup_driver`](main.py).
3. Untuk setiap port dan bulan, buat URL lalu proses lewat [`main.process_port_month`](main.py).
4. Fungsi scraping rinci ada di modul [utils.py](utils.py):
   - [`utils.get_detail_links`](utils.py)
   - [`utils.get_nomor_produk_list`](utils.py)
   - [`utils.scrape_detail_data`](utils.py)
5. Hasil dikumpulkan lalu:
   - diunggah ke GCS via [`main.upload_to_gcs_json`](main.py)
   - dimuat ke BigQuery via [`main.upload_to_bigquery_json`](main.py)

Jalankan lokal (development)
1. Buat virtualenv:
   python -m venv env
   source env/bin/activate
2. Install deps:
   pip install -r requirements.txt
3. Set kredensial GCP:
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
4. Jalankan fungsi lokal (contoh: gunakan Functions Framework):
   pip install functions-framework
   functions-framework --target=scrape_inaportnet

Deployment ke Cloud Functions
Contoh deploy:
gcloud functions deploy scrape_inaportnet \
  --runtime python310 \
  --trigger-http \
  --allow-unauthenticated \
  --entry-point scrape_inaportnet \
  --region <REGION> \
  --project <PROJECT>

(Atur variabel environment atau perbarui [config.ini](config.ini) sesuai kebutuhan)

Docker
------
Dockerfile ada di repo; build & run container untuk environment headless Chrome yang konsisten:
docker build -t inaportnet-scraper .
docker run --env GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json -v /local/key.json:/path/to/key.json inaportnet-scraper

Troubleshooting singkat
----------------------
- Chrome driver error: pastikan versi Chrome & chromedriver kompatibel.
- Izin GCP: service account harus punya akses write ke bucket dan BigQuery load.
- Tidak ada data: periksa [ports.csv](ports.csv) dan format months di [config.ini](config.ini).

Referensi kode
--------------
- Entry point dan pipeline: [`main.py`](main.py)
- Helper scraping: [`utils.py`](utils.py)
- Konfigurasi: [`config.ini`](config.ini)
- Requirements: [`requirements.txt`](requirements.txt)
- Docker: [`Dockerfile`](Dockerfile)
