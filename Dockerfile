# ==============================================================================
# Stage 1: Builder
# Installa le dipendenze in un ambiente isolato per mantenere l'immagine finale leggera
# ==============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Copia solo il requirements.txt prima per sfruttare la cache di Docker
COPY requirements.txt .

# Installa le dipendenze in una directory separata
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ==============================================================================
# Stage 2: Runner (immagine finale)
# ==============================================================================
FROM python:3.12-slim AS runner

WORKDIR /app

# Copia le dipendenze pre-installate dallo stage builder
COPY --from=builder /install /usr/local

# Copia il codice sorgente dell'applicazione
COPY src/ ./src/
COPY config.yaml ./config.yaml

# Variabili d'ambiente con valori di default (sovrascrivibili al runtime)
# Le credenziali sensibili NON devono essere hardcoded qui:
# usare -e o --env-file al lancio del container.
ENV CONFIG_PATH=/app/config.yaml
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Il listener ascolta sulla porta 8000
EXPOSE 8000

# Utente non-root per ridurre la superficie d'attacco
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# Comando di avvio tramite Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
