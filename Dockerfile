# Użyj lekkiego obrazu z Pythonem
FROM python:3.11-slim

# Ustaw zmienną środowiskową na nieinteraktywną instalację pakietów
ENV DEBIAN_FRONTEND=noninteractive

# Ustaw katalog roboczy
WORKDIR /app

# Skopiuj pliki do kontenera
COPY . /app

# Zainstaluj zależności z requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Wystaw port Flask (zmień jeśli używasz innego)
EXPOSE 5000

# Uruchom aplikację
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
