# Python 3.11 tabanlı resmi ve hafif (slim) imajı kullanıyoruz
FROM python:3.11-slim

# Çalışma dizinini ayarlıyoruz
WORKDIR /app

# İşletim sistemi seviyesinde gerekli olabilecek bağımlılıkları yüklüyoruz
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Requirements dosyasını kopyalayıp bağımlılıkları yüklüyoruz
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodlarını kopyalıyoruz
COPY . .

# Flask'ın varsayılan portu olan 5000 portunu dışa açıyoruz
EXPOSE 5000

# Çevresel değişkenleri ayarlıyoruz (Production modu için)
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Uygulamayı Gunicorn (üretim seviyesi sunucu) ile başlatıyoruz
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "app:app"]
