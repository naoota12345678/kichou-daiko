FROM python:3.11-slim

# Playwright dependencies
RUN apt-get update && apt-get install -y \
    wget gnupg2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

COPY . .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
