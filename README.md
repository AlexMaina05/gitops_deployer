# 🚀 GitOps Auto-Deployer

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23692700.svg)](https://doi.org/10.5281/zenodo.23692700)
[![CI](https://github.com/AlexMaina05/gitops_deployer/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexMaina05/gitops_deployer/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-v2-2496ED.svg)](https://docs.docker.com/compose/)
[![Tests](https://img.shields.io/badge/tests-118%20passed-brightgreen.svg)]()
[![Security](https://img.shields.io/badge/HMAC--SHA256-Strict-orange.svg)]()
[![ORCID](https://img.shields.io/badge/ORCID-0009--0003--7003--7247-green.svg)](https://orcid.org/0009-0003-7003-7247)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Un microservizio snello, asincrono e ad alta affidabilità sviluppato in **Python** con **FastAPI** e **Uvicorn**, progettato per automatizzare il deployment continuo (*Continuous Deployment*) di stack applicativi containerizzati su server e virtual machine self-hosted.

Ascolta gli eventi Webhook generati dai provider Git (**GitHub**, **Gitea/Forgejo** o **GitLab** tramite proxy/pipeline), autentica crittograficamente ogni singola richiesta mediante firme **HMAC-SHA256** e aggiorna automaticamente i container eseguendo in sicurezza la sequenza:
$$\text{git pull origin main} \longrightarrow \text{docker compose pull} \longrightarrow \text{docker compose up -d}$$

Al termine di ciascuna operazione, invia notifiche dettagliate in tempo reale verso **Telegram** (con messaggi grafici formattati in HTML) e **n8n** (con payload JSON strutturati per automazioni DevOps avanzate).

---

## 📑 Indice della Documentazione Approfondita

La documentazione ufficiale è organizzata in guide tematiche modulari consultabili nella cartella [`docs/`](./docs/):

| Documento | Descrizione dei Contenuti |
| :--- | :--- |
| ✅ [**Checklist Pre-Deploy**](./docs/prerequisiti.md) | **Inizia da qui.** Tutto ciò che devi raccogliere prima di configurare il server: come generare il webhook secret, come ottenere il Bot Token Telegram e il Chat ID, come creare il Webhook n8n, e un template pronto del `config.yaml` da compilare. |
| 📐 [**Architettura di Sistema**](./docs/architettura.md) | Ciclo di vita della richiesta, interazione tra moduli FastAPI, crittografia HMAC, prevenzione command injection ed eliminazione dei *retry storm* tramite gestione semantica dei codici HTTP. |
| ⚙️ [**Guida alla Configurazione**](./docs/configurazione.md) | Riferimento completo di `config.yaml`, modelli Pydantic v2, doppio accesso oggetto/dizionario (`ConfigDict`), matrice delle variabili d'ambiente ed esempi pronti all'uso per dev e produzione. |
| 🔔 [**Guida alle Notifiche (Telegram & n8n)**](./docs/notifiche.md) | Setup passo-passo del Bot Telegram con @BotFather, recupero chat ID, template grafici con emoji, schema JSON completo per nodi Webhook n8n e principio di isolamento dei guasti (*fault isolation*). |
| 🔗 [**Integrazione Webhook Git & Sicurezza**](./docs/webhooks.md) | Configurazione dettagliata su GitHub, Gitea e GitLab (con pipeline CI/CD o relay n8n), specifiche crittografiche dell'header `X-Hub-Signature-256`, script di simulazione in Python e comandi Bash/curl. |
| 🚢 [**Deployment e Gestione Operativa**](./docs/deploy.md) | Messa in produzione con Uvicorn (perché `--workers 1` è vitale per i lock Git), file service per **systemd** con hardening di sicurezza, Reverse Proxy SSL con **Nginx** o **Caddy**, e containerizzazione Docker. |

---

## ✨ Caratteristiche Principali

- **Sicurezza Zero-Trust con HMAC-SHA256**: Verifica l'autenticità di ogni webhook confrontando il corpo binario grezzo della richiesta con l'header `X-Hub-Signature-256`. L'uso di `hmac.compare_digest` azzera il rischio di attacchi basati sui tempi di risposta (*timing attacks*).
- **Immunità da Command Injection**: L'esecutore di sistema (`src/executor.py`) invoca esclusivamente elenchi di token (`list[str]`) tramite `subprocess.run` con `shell=False`. I comandi shell non vengono mai concatenati come stringhe arbitrarie.
- **Pipeline Deterministica con Short-Circuiting**: Se la sincronizzazione Git o il download delle nuove immagini Docker fallisce, la procedura si arresta immediatamente senza compromettere i container attivi.
- **Prevenzione dei Webhook Retry Storm**: In caso di fallimento della pipeline locale, l'endpoint risponde con `HTTP 200 OK` segnalando l'esito nel payload (`{"status": "failed", "deployed": false}`). In questo modo i server Git non innescano cicli infiniti di reinvio forzato.
- **Notifiche Multi-Canale con Isolamento dei Guasti**: Supporto integrato sia per bot Telegram che per flussi di automazione n8n. Un blocco o errore su un canale non impedisce l'invio all'altro canale né influisce sull'esito della chiamata webhook.
- **Configurazione Ibrida e Flessibile**: Supporta file YAML con validazione Pydantic v2 e sovrascrittura totale tramite variabili d'ambiente (formato `.env`, Docker o systemd).

---

## 📁 Struttura Reale del Repository

```text
gitops_deployer/
├── README.md                      # Questo documento (Guida Principale e Panoramica)
├── config.yaml                    # File di configurazione applicativa attivo
├── config.example.yaml            # Modello di esempio commentato per la configurazione
├── requirements.txt               # Dipendenze Python ufficiali (FastAPI, Uvicorn, PyYAML, ecc.)
├── docs/                          # Documentazione tecnica approfondita
│   ├── architettura.md            # Architettura interna e ciclo di vita della richiesta
│   ├── configurazione.md          # Riferimento parametri Pydantic e variabili d'ambiente
│   ├── deploy.md                  # Manuale operativo di produzione (systemd, Nginx, Docker)
│   ├── notifiche.md               # Setup canali Telegram e schema JSON webhook n8n
│   └── webhooks.md                # Configurazione GitHub, Gitea, GitLab e test crittografici
├── src/                           # Moduli del microservizio
│   ├── __init__.py
│   ├── config.py                  # Caricatore configurazione YAML/Pydantic e wrapper ConfigDict
│   ├── executor.py                # Pipeline di esecuzione sicura (git pull e docker compose)
│   ├── main.py                    # Server FastAPI, endpoint /health e /webhook
│   ├── notifier.py                # Dispatcher notifiche multi-provider (Telegram e n8n)
│   └── security.py                # Verifica crittografica firma HMAC-SHA256
└── tests/                         # Suite completa di test automatizzati (TDD)
    ├── test_adversarial_notifier.py # Test di robustezza, timeout e anomalie di rete per le notifiche
    ├── test_adversarial_webhook.py  # Test crittografici di bit-flip, signature evasion e injection
    ├── test_executor.py           # Test di esecuzione comandi shell e interruzione short-circuit
    ├── test_main.py               # Test di integrazione endpoint FastAPI con TestClient
    ├── test_notifier.py           # Test sui payload HTTP e isolamento dei provider
    └── test_security.py           # Test di validazione base HMAC-SHA256
```

---

## ⚡ Guida Rapida di Avvio (Quickstart in 5 Minuti)

### 1. Clonazione e Setup dell'Ambiente Virtuale
```bash
# Clona il repository sul tuo server o macchina locale
git clone https://github.com/AlexMaina05/gitops_deployer.git
cd gitops_deployer

# Crea l'ambiente virtuale dedicato
python3 -m venv venv

# Attiva l'ambiente virtuale
# Su Linux/macOS:
source venv/bin/activate
# Su Windows (PowerShell):
# .\venv\Scripts\Activate.ps1

# Installa le dipendenze verificate
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 2. Configurazione Rapida (`config.yaml`)
Copia il file di esempio e personalizza i parametri essenziali:
```bash
cp config.example.yaml config.yaml
```

Modifica `config.yaml`:
```yaml
webhook:
  # Inserisci una password/token complessa
  secret: "la_tua_chiave_segreta_hmac_super_sicura"

deploy:
  # Percorso assoluto della cartella contenente il codice e il docker-compose.yml
  repo_path: "/opt/deployments/mia-applicazione"

notifications:
  active_targets:
    - "telegram"
    - "n8n"

  telegram:
    bot_token: "TUO_BOT_TOKEN_DA_BOTFATHER"
    chat_id: "TUO_CHAT_ID"

  n8n:
    webhook_url: "https://n8n.tuodominio.it/webhook/deploy-status"
```

---

### 3. Avvio del Server Locale
Avvia l'applicazione con Uvicorn:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

In un altro terminale, verifica che il servizio sia attivo e risponda correttamente:
```bash
curl http://127.0.0.1:8000/health
# Risposta attesa:
# {"status":"ok"}
```

---

## 🧪 Esecuzione della Suite di Test

Il progetto adotta rigorosi standard di ingegneria del software e sviluppo guidato dai test (**TDD**). La suite include test funzionali, test di integrazione con `TestClient` di FastAPI e test avversariali crittografici (bit-flip su ogni posizione dell'hash, attacchi di manipolazione degli algoritmi e guasti di rete simulati).

Per eseguire l'intera suite di test:
```bash
# Esecuzione con pytest
pytest tests/
```

Dovresti ottenere un report pulito con **118 test superati**:
```text
======================== 118 passed in 3.78s ========================
```

---

## ⚙️ Riferimento Sintetico della Configurazione

Le impostazioni possono essere fornite sia tramite `config.yaml` sia esportando variabili d'ambiente di sistema (con precedenza alle variabili d'ambiente):

| Chiave YAML | Variabile d'Ambiente | Default | Descrizione |
| :--- | :--- | :--- | :--- |
| `webhook.secret` | `WEBHOOK_SECRET` o `GITOPS_SECRET` | `"your_webhook_secret_here"` | Chiave segreta HMAC-SHA256 condivisa con il provider Git. *(Obbligatoria)* |
| `deploy.repo_path` | `REPO_PATH` o `GITOPS_REPO_PATH` | `"e:/Code/gitops_deployer"` | Percorso locale del repository Git e del file `docker-compose.yml`. |
| `notifications.active_targets` | `ACTIVE_TARGETS` | `["telegram", "n8n"]` | Elenco dei canali di notifica abilitati (`telegram`, `n8n` o entrambi). |
| `notifications.telegram.bot_token` | `TELEGRAM_BOT_TOKEN` | `""` | Token HTTP del Bot Telegram rilasciato da `@BotFather`. |
| `notifications.telegram.chat_id` | `TELEGRAM_CHAT_ID` | `""` | ID numerico della chat, gruppo o canale Telegram di destinazione. |
| `notifications.n8n.webhook_url` | `N8N_WEBHOOK_URL` | `""` | URL completo dell'endpoint Webhook in ingresso su n8n. |

*Per la specifica completa dei tipi, dell'accesso duale con `ConfigDict` e delle sintassi avanzate, consulta la [Guida alla Configurazione](./docs/configurazione.md).*

---

## 🔒 Sicurezza Crittografica & Webhook Git

Quando configuri il webhook sul tuo provider Git:
1. **Payload URL**: `https://deploy.tuodominio.it/webhook`
2. **Content type**: `application/json`
3. **Secret**: La stringa segreta configurata in `webhook.secret`.
4. **Events**: Seleziona solo gli eventi di push (*Push events*).

Ad ogni richiesta ricevuta su `POST /webhook`, il server:
1. Isola il corpo grezzo della richiesta senza alterarne la codifica binaria.
2. Calcola localmente l'hash `sha256=` tramite la chiave condivisa.
3. Esegue un confronto a tempo costante (`hmac.compare_digest`) con l'header `X-Hub-Signature-256`.
4. Se la firma non corrisponde, la richiesta viene immediatamente respinta con **`401 Unauthorized`**.

*Per istruzioni passo-passo per GitHub, Gitea e soluzioni di relay per GitLab, consulta la [Guida all'Integrazione Webhook Git](./docs/webhooks.md).*

---

## 🚢 Messa in Produzione

Per ambienti di produzione reali (server Linux Ubuntu/Debian):
- **Server ASGI**: Esegui Uvicorn con `--host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --access-log`. L'uso di un singolo worker (`--workers 1`) è indispensabile per prevenire conflitti concorrenti sul lock del repository Git (`.git/index.lock`).
- **Gestore di Processo**: Configura un servizio dedicato con **systemd** per garantire riavvio automatico al boot, isolamento dei privilegi e logging su journalctl.
- **Reverse Proxy**: Esponi il servizio su Internet esclusivamente tramite **Nginx** o **Caddy** con certificati SSL/TLS validi (Let's Encrypt), rate limiting e timeout estesi per il completamento dei download Docker.

*Per i file di configurazione pronti al copia-incolla per systemd, Nginx, Caddy e Docker Compose, consulta la [Guida al Deployment e alla Gestione in Produzione](./docs/deploy.md).*

---

## 📚 Citazione Accademica & Zenodo DOI

Se utilizzi questo software o la sua architettura nei tuoi progetti di ricerca, homelab o tesi di laurea, cita il software utilizzando i seguenti metadati (disponibili anche in formato [`CITATION.cff`](./CITATION.cff)):

```bibtex
@software{mainardi2026gitops,
  author       = {Alessandro Mainardi},
  title        = {AlexMaina05/gitops_deployer: v1.0.0},
  month        = oct,
  year         = 2026,
  publisher    = {Zenodo / CERN},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.23692700},
  url          = {https://doi.org/10.5281/zenodo.23692700},
  institution  = {Alma Mater Studiorum - Università di Bologna}
}
```

- **DOI:** [10.5281/zenodo.23692700](https://doi.org/10.5281/zenodo.23692700)
- **Autore:** [Alessandro Mainardi](https://alexmaina.dev/) (ORCID: [0009-0003-7003-7247](https://orcid.org/0009-0003-7003-7247), Wikidata: [Q141886579](https://www.wikidata.org/wiki/Q141886579))
- **Affiliazione:** DISI — Alma Mater Studiorum Università di Bologna

---

## 📄 Licenza

Rilasciato sotto licenza open source **[MIT License](./LICENSE)**. Copyright © 2026 Alessandro Mainardi.
