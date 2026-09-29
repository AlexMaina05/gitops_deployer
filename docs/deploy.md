# Guida Operativa al Deployment e alla Gestione in Produzione

Questo documento illustra l'installazione, la configurazione, la messa in produzione e la manutenzione operativa di **GitOps Auto-Deployer** in diversi scenari di deployment (dall'ambiente di sviluppo locale fino a cluster di produzione gestiti con **systemd**, **Docker** e **Reverse Proxy HTTPS**).

---

## 1. Prerequisiti di Sistema

Per eseguire correttamente il microservizio e consentire a `src/executor.py` di orchestrare i deployment locali, il server deve disporre dei seguenti componenti software:

1. **Python 3.11 o superiore**:
   - Verificabile con `python3 --version` (o `python --version` su Windows).
   - Richiede il gestore pacchetti `pip` e il modulo `venv`.
2. **Git**:
   - Installato e disponibile nella variabile di ambiente `$PATH` del sistema.
   - Verificabile con `git --version`.
   - Il repository locale target deve avere il remote configurato come `origin` e il branch tracciato deve essere `main`.
3. **Docker Engine e Docker Compose Plugin v2**:
   - Docker Engine versione 20.10+ in esecuzione (`docker --version`).
   - Plugin Docker Compose v2 (`docker compose version`). *Nota: il software esegue il comando `docker compose` (con lo spazio), non il vecchio binario `docker-compose` standalone v1.*
4. **Permessi Utente (Gruppo `docker`)**:
   - L'utente di sistema che esegue il microservizio deve appartenere al gruppo di sistema `docker` per poter comunicare con il socket UNIX `/var/run/docker.sock` senza privilegi di `sudo`:
     ```bash
     sudo usermod -aG docker <nome_utente>
     ```

---

## 2. Esecuzione in Ambiente di Sviluppo Locale

Per sviluppare, testare nuove funzionalità o verificare le notifiche sulla propria workstation:

### 2.1 Creazione dell'Ambiente Virtuale e Installazione
- **Su Linux / macOS:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  ```

- **Su Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  ```

### 2.2 Avvio del Server in Modalità Sviluppo
Avvia Uvicorn con il flag `--reload` per ricaricare automaticamente l'applicazione ad ogni modifica dei file sorgente:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

In alternativa, è possibile avviare direttamente il modulo:
```bash
python -m src.main
```

Verifica che il server risponda interrogando l'endpoint di stato:
```bash
curl http://127.0.0.1:8000/health
# Risposta: {"status":"ok"}
```

---

## 3. Esecuzione in Produzione con Uvicorn

In ambiente di produzione, la linea di comando consigliata per avviare Uvicorn è la seguente:

```bash
uvicorn src.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --access-log
```

### Perché il parametro `--workers 1` è Tassativo?
Una domanda frequente nell'ottimizzazione di applicazioni FastAPI è il motivo per cui si raccomanda l'uso di un **singolo worker** invece del classico $2 \times \text{CPU} + 1$:

1. **Lock Esclusivo sul Repository Git**:  
   Quando `src/executor.py` esegue `git pull origin main`, il client Git crea temporaneamente il file `.git/index.lock` per garantire la consistenza dell'indice.
2. **Conflitti di Concorrenza (Race Conditions)**:  
   Se più worker Uvicorn ricevessero webhook quasi simultanei (ad esempio in caso di push frequenti o retry), verrebbero avviati molteplici comandi `git pull` paralleli all'interno della stessa directory fisica (`repo_path`). Il secondo processo fallirebbe istantaneamente con l'errore:
   ```text
   fatal: Unable to create '/path/to/repo/.git/index.lock': File exists.
   ```
3. **Serializzazione Deterministica**:  
   Un singolo worker Uvicorn accoda le richieste HTTP in ingresso e serializza l'esecuzione dei comandi shell, garantendo che ogni `git pull`, `docker compose pull` e `docker compose up -d` avvenga in modo sequenziale, isolato e senza alcuna collisione di lock.

### Flag Aggiuntivi di Uvicorn Spiegati
- `--host 127.0.0.1`: Limita l'ascolto alla sola interfaccia di loopback locale. Il microservizio non viene esposto direttamente su Internet, ma solo al Reverse Proxy locale (Nginx/Caddy).
- `--proxy-headers`: Istruisce Uvicorn a considerare attendibili gli header `X-Forwarded-For` e `X-Forwarded-Proto` forniti dal Reverse Proxy.
- `--access-log`: Mantiene un registro dettagliato degli accessi HTTP con timestamp e IP chiamante, essenziale per monitorare e verificare le chiamate webhook dei provider Git.

---

## 4. Installazione come Servizio di Sistema (Systemd su Linux)

La modalità di deployment nativa consigliata su server Linux (Ubuntu, Debian, AlmaLinux, Rocky) consiste nell'installazione come demone di sistema gestito da **systemd**.

### 4.1 Creazione dell'Utente di Servizio e delle Cartelle
```bash
# Crea un utente di sistema dedicato denominato 'deployer'
sudo useradd -r -s /bin/bash -d /opt/gitops_deployer -m deployer
sudo usermod -aG docker deployer

# Copia i sorgenti nella directory applicativa
sudo mkdir -p /opt/gitops_deployer
sudo cp -r . /opt/gitops_deployer/
sudo chown -R deployer:deployer /opt/gitops_deployer

# Crea il virtualenv per l'utente deployer
sudo -u deployer python3 -m venv /opt/gitops_deployer/venv
sudo -u deployer /opt/gitops_deployer/venv/bin/pip install --upgrade pip
sudo -u deployer /opt/gitops_deployer/venv/bin/pip install -r /opt/gitops_deployer/requirements.txt
```

### 4.2 File Unit Systemd con Hardening di Sicurezza
Crea il file `/etc/systemd/system/gitops-deployer.service`:

```ini
[Unit]
Description=GitOps Auto-Deployer Microservice
Documentation=https://github.com/tuo-account/gitops_deployer
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=deployer
Group=deployer
WorkingDirectory=/opt/gitops_deployer

# Percorso dei binari nell'ambiente virtuale e variabili
Environment="PATH=/opt/gitops_deployer/venv/bin:/usr/local/bin:/usr/bin"
EnvironmentFile=-/opt/gitops_deployer/.env

# Comando di avvio Uvicorn
ExecStart=/opt/gitops_deployer/venv/bin/uvicorn src.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1 \
    --proxy-headers \
    --access-log

# Politica di riavvio automatico in caso di crash imprevisto
Restart=always
RestartSec=5s

# Direttive di Hardening di Sicurezza
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 4.3 Gestione del Servizio
```bash
# Ricarica la configurazione di systemd
sudo systemctl daemon-reload

# Abilita l'avvio automatico al boot del sistema
sudo systemctl enable gitops-deployer

# Avvia il servizio
sudo systemctl start gitops-deployer

# Verifica lo stato
sudo systemctl status gitops-deployer

# Visualizzazione dei log in tempo reale
sudo journalctl -u gitops-deployer -f
```

---

## 5. Configurazione del Reverse Proxy e Terminazione SSL/TLS

L'endpoint webhook deve essere esposto a Internet tramite **HTTPS** con un certificato SSL/TLS valido (ad es. rilasciato gratuitamente da Let's Encrypt), poiché i provider come GitHub richiedono o raccomandano rigorosamente connessioni cifrate.

### 5.1 Configurazione con Nginx (con Rate Limiting e Timeout Estesi)
Crea il file `/etc/nginx/sites-available/gitops.conf`:

```nginx
# Definizione della zona di rate limiting per prevenire abusi (max 10 richieste al minuto per IP)
limit_req_zone $binary_remote_addr zone=gitops_rate:10m rate=10r/m;

# Reindirizzamento da HTTP a HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name deploy.tuodominio.it;

    return 301 https://$host$request_uri;
}

# Blocco HTTPS principale
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name deploy.tuodominio.it;

    # Certificati Let's Encrypt (gestiti tramite certbot)
    ssl_certificate /etc/letsencrypt/live/deploy.tuodominio.it/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/deploy.tuodominio.it/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        # Applicazione del rate limiting (ammette burst di 5 richieste)
        limit_req zone=gitops_rate burst=5 nodelay;

        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Header di inoltro proxy standard
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout estesi: necessari affinché il reverse proxy non chiuda
        # la connessione mentre git pull e docker compose pull scaricano i dati
        proxy_connect_timeout 60s;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

Abilita il sito e ricarica Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/gitops.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

### 5.2 Alternativa Moderna con Caddy
Se utilizzi **Caddy**, il provisioning e il rinnovo dei certificati TLS con Let's Encrypt sono completamente automatici.

Aggiungi al tuo `Caddyfile`:

```caddy
deploy.tuodominio.it {
    reverse_proxy 127.0.0.1:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-Port {server_port}
        transport http {
            response_header_timeout 300s
        }
    }
}
```

Ricarica Caddy:
```bash
sudo systemctl reload caddy
```

---

## 6. Deployment Containerizzato con Docker

Se preferisci eseguire GitOps Auto-Deployer all'interno di un container Docker dedicato, è necessario concedere al container l'accesso al socket Docker dell'host e alla directory del repository target.

### 6.1 `Dockerfile`
```dockerfile
FROM python:3.11-slim

# Installazione delle dipendenze di sistema: git, curl e client Docker Compose v2
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends \
       docker-ce-cli \
       docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia dei requisiti e installazione
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia del codice sorgente
COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

---

### 6.2 `docker-compose.deployer.yml`
```yaml
version: "3.8"

services:
  gitops-deployer:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: gitops-auto-deployer
    restart: unless-stopped
    ports:
      # Esposizione unicamente sull'interfaccia di loopback locale
      - "127.0.0.1:8000:8000"
    volumes:
      # Montaggio del socket Docker dell'host per consentire comandi docker compose
      - /var/run/docker.sock:/var/run/docker.sock
      # Montaggio del repository target da aggiornare
      - /opt/deployments/production-app:/opt/deployments/production-app
      # Montaggio opzionale della chiave SSH per git pull da repo privati
      - /root/.ssh:/root/.ssh:ro
      # File di configurazione
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - CONFIG_PATH=/app/config.yaml
```

Avvio del container:
```bash
docker compose -f docker-compose.deployer.yml up -d --build
```

### ⚠️ Considerazioni Critiche di Sicurezza sul Socket Docker
Montare `/var/run/docker.sock` all'interno di un container equivale a concedere privilegi di `root` completi sull'host ospitante, poiché chiunque possa interagire con l'API Docker può creare container privilegiati con accesso al filesystem dell'host.
- **Rigorosa Protezione HMAC**: Non disabilitare mai o indebolire la chiave segreta `webhook.secret`.
- **Rete Isolata**: Assicurati che la porta 8000 sia vincolata tassativamente a `127.0.0.1` e non a `0.0.0.0`, affidando l'accesso dall'esterno esclusivamente al Reverse Proxy autenticato via HTTPS.
