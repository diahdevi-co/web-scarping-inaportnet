# Gunakan base image dengan Python + Chrome + Functions Framework
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Install Chrome & dependencies
RUN apt-get update && apt-get install -y wget gnupg unzip curl \
    && apt-get install -y chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy semua file project
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8080 untuk Cloud Run
EXPOSE 8080

# Jalankan Cloud Function HTTP menggunakan Functions Framework
CMD ["functions-framework", "--target=scrape_inaportnet", "--port=8080"]
