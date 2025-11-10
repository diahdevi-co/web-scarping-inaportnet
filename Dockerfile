# Gunakan base image dengan Python + Chrome + Functions Framework
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Install Chrome & dependencies
RUN apt-get update && apt-get install -y wget gnupg \
    && mkdir -p /etc/apt/keyrings \
    && wget -q -O /etc/apt/keyrings/google-linux-signing-key.gpg https://dl.google.com/linux/linux_signing_key.pub \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-linux-signing-key.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
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
