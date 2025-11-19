FROM python:3.11-slim

ENV PYTHONUNBUFFERED=True
ENV PORT=8080
ENV CHROME_VERSION=131.0.6778.87

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget unzip gnupg curl \
    fonts-liberation libasound2 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libnspr4 libnss3 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libatspi2.0-0 libxshmfence1 libx11-xcb1 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install specific Chrome version
RUN wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    -O /tmp/chrome.zip && \
    unzip -q /tmp/chrome.zip -d /opt && \
    ln -s /opt/chrome-linux64/chrome /usr/bin/google-chrome && \
    rm /tmp/chrome.zip

# Install matching ChromeDriver
RUN wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip" \
    -O /tmp/chromedriver.zip && \
    unzip -q /tmp/chromedriver.zip -d /tmp && \
    mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf /tmp/chromedriver* && \
    \
    # Verify versions
    echo "Chrome version:" && google-chrome --version && \
    echo "ChromeDriver version:" && chromedriver --version

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create default config.ini if not exists
RUN if [ ! -f config.ini ]; then \
    echo "[gcp]" > config.ini && \
    echo "bucket_name=exampletesting9999" >> config.ini && \
    echo "project_id=corporate-digital" >> config.ini && \
    echo "dataset=DIGITAL_INTERNSHIP" >> config.ini && \
    echo "table=inaportnet_scraped_data" >> config.ini; \
    fi

# Verify required files exist
RUN ls -la && \
    test -f main.py && echo "main.py exists" || echo "main.py missing" && \
    test -f utils.py && echo "utils.py exists" || echo "utils.py missing" && \
    test -f config.ini && echo "config.ini exists" || echo "config.ini missing"

# Start the functions framework
CMD exec functions-framework --target=scrape_inaportnet --host=0.0.0.0 --port=${PORT}
