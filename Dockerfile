# Gunakan base image Python slim untuk efisiensi
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependency OS (Chrome + Selenium)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome dan ChromeDriver
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies dan install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh project
COPY . .

# Set environment variable agar Chrome bisa jalan di mode headless di container
ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    CHROME_BIN=/usr/bin/google-chrome \
    GOOGLE_APPLICATION_CREDENTIALS=/app/service-account.json

# Jalankan script utama
CMD ["python", "main.py"]
