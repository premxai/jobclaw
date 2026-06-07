FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps for curl_cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libcurl4-openssl-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

# Create data directory for SQLite
RUN mkdir -p data

EXPOSE 8000

CMD ["python", "scripts/worker/standalone_worker.py"]
