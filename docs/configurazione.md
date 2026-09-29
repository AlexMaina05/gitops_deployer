# Guida Completa alla Configurazione

La configurazione di **GitOps Auto-Deployer** è gestita attraverso il modulo `src/config.py`, che combina la flessibilità di file di configurazione in formato **YAML** con la potenza della validazione dei dati offerta da **Pydantic v2**. 

Il sistema consente inoltre di sovrascrivere qualsiasi parametro a runtime tramite **variabili d'ambiente**, rendendo il servizio ideale per ambienti containerizzati (Docker/Kubernetes), macchine virtuali gestite con systemd o ambienti di sviluppo locale.

---

## 1. Meccanismo di Caricamento e Risoluzione

La funzione principale incaricata di inizializzare la configurazione è `load_config(config_path: Optional[str] = "config.yaml") -> ConfigDict`.

### Ordine di Risoluzione del Percorso File
1. **Argomento esplicito**: parametro `config_path` passato programmaticamente alla funzione `load_config()`.
2. **Variabile d'ambiente `CONFIG_PATH`**: se impostata (es. `CONFIG_PATH=/etc/gitops/config.yaml`), viene utilizzata come percorso prioritario.
3. **Valore predefinito di fallback**: file `config.yaml` posizionato nella root directory di esecuzione del microservizio.

Se il file YAML indicato non esiste o contiene errori di sintassi, il caricatore emette un messaggio di log appropriato e inizializza il modello con i valori predefiniti di fabbrica.

### Gerarchia di Precedenza dei Valori
Quando un parametro è definito in più posizioni, l'ordine di priorità decrescente è:
$$\text{Variabili d'Ambiente} > \text{File YAML} > \text{Valori Predefiniti Pydantic}$$

---

## 2. Riferimento Completo dei Parametri

Di seguito è riportata la specifica esaustiva di ciascuna chiave disponibile nel file di configurazione YAML, con il relativo tipo di dato, valore di default e vincoli operativi.

| Percorso Chiave YAML | Tipo | Default Pydantic | Obbligatorio a Runtime | Descrizione Funzionale |
| :--- | :--- | :--- | :--- | :--- |
| `webhook.secret` | `str` | `"your_webhook_secret_here"` | **Sì** | Token segreto condiviso con il provider Git per la verifica della firma HMAC-SHA256 (`X-Hub-Signature-256`). Se vuoto o assente, il servizio rifiuta qualsiasi richiesta con HTTP 401. |
| `deploy.repo_path` | `str` | `"e:/Code/gitops_deployer"` | **Sì** | Percorso assoluto o relativo sul filesystem locale in cui risiede il repository Git clonato e il file `docker-compose.yml`. |
| `notifications.active_targets` | `List[str]` | `["telegram", "n8n"]` | No | Elenco dei canali di notifica abilitati. Valori riconosciuti: `"telegram"`, `"n8n"`. Se impostato su lista vuota `[]`, le notifiche sono disabilitate. |
| `notifications.telegram.bot_token` | `str` | `""` | Sì (se Telegram è attivo) | Token API univoco del Bot Telegram rilasciato da `@BotFather`. |
| `notifications.telegram.chat_id` | `str` | `""` | Sì (se Telegram è attivo) | ID numerico o alfanumerico della chat, gruppo o canale Telegram di destinazione. |
| `notifications.n8n.webhook_url` | `str` | `""` | Sì (se n8n è attivo) | URL HTTP/HTTPS dell'endpoint Webhook in ingresso configurato nel workflow n8n. |

---

## 3. Matrice delle Variabili d'Ambiente (Override)

Ogni impostazione del file YAML può essere sovrascritta impostando le rispettive variabili d'ambiente. Ciò è particolarmente utile in ambienti di produzione (tramite file `.env`, direttive `Environment` di systemd, o chiavi `environment` in Docker Compose) per non dover includere credenziali e secret all'interno del controllo versione Git.

| Modello Pydantic | Chiave YAML Corrispondente | Variabile d'Ambiente Supportata | Logica di Parsing ed Esempi |
| :--- | :--- | :--- | :--- |
| `webhook.secret` | `webhook.secret` | `WEBHOOK_SECRET` oppure `GITOPS_SECRET` | Assegnazione diretta come stringa. Se entrambe sono presenti, `WEBHOOK_SECRET` ha la precedenza. |
| `deploy.repo_path` | `deploy.repo_path` | `REPO_PATH` oppure `GITOPS_REPO_PATH` | Assegnazione diretta come stringa (es. `/opt/deployments/my-service`). |
| `notifications.telegram.bot_token` | `notifications.telegram.bot_token` | `TELEGRAM_BOT_TOKEN` | Assegnazione diretta stringa (es. `123456789:ABCdefGHI...`). |
| `notifications.telegram.chat_id` | `notifications.telegram.chat_id` | `TELEGRAM_CHAT_ID` | Assegnazione diretta stringa (es. `987654321` o `-1001234567890`). |
| `notifications.n8n.webhook_url` | `notifications.n8n.webhook_url` | `N8N_WEBHOOK_URL` | Assegnazione diretta stringa URL (es. `https://n8n.mio-dominio.it/webhook/deploy`). |
| `notifications.active_targets` | `notifications.active_targets` | `ACTIVE_TARGETS` | **Doppia sintassi supportata:**<br>1. Array JSON: `["telegram"]` o `["telegram", "n8n"]`<br>2. Stringa separata da virgole: `telegram, n8n` oppure solo `telegram`. Gli spazi e le maiuscole/minuscole vengono normalizzati automaticamente. |

---

## 4. Modalità di Accesso Duale: `ConfigDict`

La funzione `load_config()` restituisce un'istanza della classe `ConfigDict` (definita in `src/config.py`). 

Questa classe estende il tipo nativo `dict` di Python sovrascrivendo i metodi speciali `__getattr__` e `__setattr__`. La funzione helper ricorsiva `_wrap_dict()` converte tutti i dizionari annidati in oggetti `ConfigDict`.

Grazie a questo pattern architetturale, gli sviluppatori e i moduli interni possono accedere alle chiavi di configurazione indifferentemente tramite:

### 1. Notazione ad Oggetto (Attributi)
```python
from src.config import load_config

config = load_config()

# Accesso orientato agli oggetti pulito e leggibile
secret = config.webhook.secret
repo_directory = config.deploy.repo_path
bot_token = config.notifications.telegram.bot_token
active = config.notifications.active_targets
```

### 2. Notazione a Dizionario Tradizionale (Indici / `.get()`)
```python
from src.config import load_config

config = load_config()

# Piena compatibilità con codice basato su dizionari standard
secret = config["webhook"]["secret"]
repo_directory = config.get("deploy", {}).get("repo_path")
bot_token = config["notifications"]["telegram"]["bot_token"]
```

Se si tenta di accedere come attributo a una chiave inesistente (es. `config.webhook.porta`), `ConfigDict` intercetta il `KeyError` interno e solleva un `AttributeError` esplicito:
`AttributeError: 'ConfigDict' object has no attribute 'porta'`.

---

## 5. Esempi Concreti di `config.yaml`

### 5.1 Esempio per Ambiente di Sviluppo Locale (`config.dev.yaml`)
Questo file è ottimizzato per il test locale su macchina di sviluppo, disattivando o puntando a un server n8n di test locale e puntando alla directory di sviluppo corrente.

```yaml
# =====================================================================
# GitOps Auto-Deployer - Configurazione Sviluppo Locale
# =====================================================================

webhook:
  # Secret di test noto per simulare richieste curl
  secret: "sviluppo_super_secret_token_12345"

deploy:
  # Percorso assoluto o relativo del repository locale su cui testare i comandi
  repo_path: "."

notifications:
  # In ambiente di sviluppo è possibile disabilitare Telegram e tenere solo n8n o viceversa
  active_targets:
    - "telegram"
    - "n8n"

  telegram:
    # Lasciare vuoto se non si desidera testare l'invio su Telegram
    bot_token: "123456789:AAFakeTokenForDevelopmentTestingOnly"
    chat_id: "99887766"

  n8n:
    # Endpoint n8n in esecuzione in locale o su porta dedicata
    webhook_url: "http://localhost:5678/webhook-test/gitops-deploy"
```

---

### 5.2 Esempio per Ambiente di Produzione (`config.prod.yaml`)
Configurazione completa per un server Linux di produzione (ad es. Debian/Ubuntu con percorsi standard in `/opt/deployments`).

```yaml
# =====================================================================
# GitOps Auto-Deployer - Configurazione Produzione Linux
# =====================================================================

webhook:
  # Generare un token sicuro a 64 caratteri (es. openssl rand -hex 32)
  secret: "9f8a3c2b1e0d4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a"

deploy:
  # Percorso assoluto del repository di produzione contenente docker-compose.yml
  repo_path: "/opt/deployments/production-app"

notifications:
  # Notifica entrambi i canali contemporaneamente
  active_targets:
    - "telegram"
    - "n8n"

  telegram:
    # Token ufficiale generato con @BotFather
    bot_token: "7123456789:ABCDefghIJKlmNoPQRstuVWXyz123456789"
    # ID chat o canale Telegram (i canali/supergruppi usano prefisso -100)
    chat_id: "-1001987654321"

  n8n:
    # Webhook di produzione esposto sotto HTTPS con certificato valido
    webhook_url: "https://n8n.tuodominio.it/webhook/deploy-production-status"
```

---

### 5.3 Esempio di Configurazione tramite File `.env` (Solo Variabili d'Ambiente)
In alternativa al file YAML, è possibile configurare interamente il microservizio esportando variabili d'ambiente (ad esempio tramite un file `/opt/gitops_deployer/.env` letto da systemd o Docker):

```bash
# File: .env
WEBHOOK_SECRET=9f8a3c2b1e0d4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a
REPO_PATH=/opt/deployments/production-app
ACTIVE_TARGETS=telegram,n8n
TELEGRAM_BOT_TOKEN=7123456789:ABCDefghIJKlmNoPQRstuVWXyz123456789
TELEGRAM_CHAT_ID=-1001987654321
N8N_WEBHOOK_URL=https://n8n.tuodominio.it/webhook/deploy-production-status
```
