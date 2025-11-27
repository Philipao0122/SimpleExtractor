FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Sistema base necesario para Selenium + Tesseract
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libtesseract-dev \
      chromium \
      chromium-driver \
      fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código de la app
COPY . .

ENV TESSERACT_PATH=/usr/bin/tesseract \
    CHROME_BINARY=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    FLASK_APP=app.py \
    MAIN_APP_PORT=5000

EXPOSE 5000

CMD ["python", "app.py"]
