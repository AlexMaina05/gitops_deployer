# Architettura di Sistema e Ciclo di Vita delle Richieste

Il microservizio **GitOps Auto-Deployer** è un'applicazione web asincrona basata su **FastAPI** e servita tramite **Uvicorn**, progettata per automatizzare il ciclo di vita del deployment continuo (Continuous Deployment) per stack containerizzati gestiti con Docker Compose e repository Git.

Questo documento fornisce un'analisi tecnica dettagliata dell'architettura interna, delle interazioni tra moduli, del modello di sicurezza crittografico, della pipeline di esecuzione comandi e della gestione dei codici di risposta HTTP.

---

## 1. Panoramica Architetturale

L'obiettivo fondamentale dell'architettura è fungere da ricevitore webhook altamente sicuro, deterministico e resiliente ai guasti. Il servizio riceve notifiche di push da provider Git (quali GitHub o Gitea), convalida l'integrità e l'autenticità del payload mediante firme HMAC-SHA256, sincronizza il codice sorgente locale, aggiorna le immagini Docker, riavvia i container e notifica l'esito a Telegram e/o n8n.

### Diagramma di Flusso End-to-End

```
+------------------+
|   Git Provider   |
| (GitHub / Gitea) |
+--------+---------+
         |
         | HTTP POST /webhook
         | Header: X-Hub-Signature-256
         | Body: Raw JSON Payload
         v
+-----------------------------------------------------------------+
|                       FastAPI (src/main.py)                     |
|                                                                 |
| 1. Risoluzione Configurazione (app.state.config o load_config)  |
| 2. Verifica presenza secret_token non vuoto                     |
| 3. Estrazione header X-Hub-Signature-256                        |
+--------------------------------+--------------------------------+
                                 |
                                 v
+-----------------------------------------------------------------+
|                    Modulo Sicurezza (src/security.py)           |
|                                                                 |
| - Calcolo HMAC-SHA256 sul corpo binario grezzo (raw bytes)      |
| - Confronto a tempo costante con hmac.compare_digest            |
+--------------------------------+--------------------------------+
                                 |
            +--------------------+--------------------+
            |                                         |
    [Firma NON Valida]                         [Firma Valida]
            |                                         |
            v                                         v
   HTTP 401 Unauthorized             +--------------------------------+
   {"detail": "Invalid signature"}   |  Motore Esecuzione             |
                                     |  (src/executor.py: deploy)     |
                                     +----------------+---------------+
                                                      |
                  +-----------------------------------+-----------------------------------+
                  |                                   |                                   |
                  v                                   v                                   v
          1. git pull origin main             2. docker compose pull             3. docker compose up -d
          [cwd=repo_path, shell=False]        [cwd=repo_path, shell=False]        [cwd=repo_path, shell=False]
                  |                                   |                                   |
                  +-----------------+-----------------+-----------------------------------+
                                    |
                            [Esito Pipeline]
                            (True o False)
                                    |
                                    v
+---------------------------------------------------------------------------------------------------------+
|                                    Sottosistema Notifiche (src/notifier.py)                             |
|                                                                                                         |
| - Isolamento Guasti (try/except separati per ciascun target)                                            |
|                                                                                                         |
|            +----------------------------------+----------------------------------+                      |
|            |                                                                     |                      |
|            v                                                                     v                      |
|  [Target: Telegram]                                                    [Target: n8n]                    |
|  - Validazione bot_token e chat_id                                      - Validazione webhook_url       |
|  - Sanitizzazione HTML (html.escape)                                    - Payload JSON strutturato      |
|  - POST api.telegram.org/bot<token>/sendMessage                         - POST webhook_url              |
|  - Icone dinamiche (🚀 SUCCESS / ❌ FAILED)                             - status: "success"/"failure"   |
+---------------------------------------------------+-----------------------------------------------------+
                                                    |
                                                    v
                                    +-------------------------------+
                                    |   Risposta HTTP 200 OK        |
                                    |   {"status": "...",           |
                                    |    "deployed": bool}          |
                                    +-------------------------------+
```

---

## 2. Moduli Interni e Responsabilità

Il codice sorgente è organizzato in moduli altamente coesi e a basso accoppiamento all'interno della cartella `src/`:

```text
src/
├── __init__.py
├── config.py       # Validazione schemi Pydantic v2 e caricamento configurazione
├── executor.py     # Esecutore comandi shell sicuro (subprocess isolation)
├── main.py         # Router FastAPI, gestione endpoint /health e /webhook
├── notifier.py     # Dispatcher notifiche multi-provider (Telegram e n8n)
└── security.py     # Logica crittografica di verifica firma HMAC-SHA256
```

### 2.1 Router Applicativo (`src/main.py`)
`src/main.py` istanzia l'applicazione FastAPI (`title="GitOps Auto-Deployer", version="1.0.0"`). Le sue responsabilità includono:
- Esporre l'endpoint di liveness/readiness `GET /health`.
- Ricevere le chiamate su `POST /webhook`.
- Isolare il payload grezzo (`await request.body()`) prima di qualsiasi parsing, preservando l'integrità byte-per-byte per la verifica crittografica.
- Gestire il fallback della configurazione tra lo stato locale dell'istanza (`request.app.state.config`) e il caricatore su file (`load_config()`).
- Coordinare in modo ordinato la sequenza: Sicurezza $\rightarrow$ Esecuzione $\rightarrow$ Notifica $\rightarrow$ Risposta HTTP.

### 2.2 Modulo di Configurazione (`src/config.py`)
Costruito su **Pydantic v2**, modella l'intera struttura dei parametri applicativi:
- Fornisce validazione rigorosa dei tipi (`BaseModel`).
- Supporta il caricamento da file YAML (`config.yaml` o percorso specificato dalla variabile d'ambiente `CONFIG_PATH`).
- Applica in cascata le variabili d'ambiente sovrascriventi (`WEBHOOK_SECRET`, `REPO_PATH`, `TELEGRAM_BOT_TOKEN`, ecc.).
- Incapsula i dati in un oggetto `ConfigDict`, consentendo il doppio accesso: come attributo ad oggetti (`config.webhook.secret`) e come chiave di dizionario standard (`config["webhook"]["secret"]`).

### 2.3 Modulo di Sicurezza Crittografica (`src/security.py`)
Il modulo `src/security.py` espone la funzione:
```python
def verify_github_signature(payload_body: bytes, secret_token: str, signature_header: str) -> bool:
```
Caratteristiche operative fondamentali:
1. **Calcolo della Firma Attesa**: Genera l'hash HMAC-SHA256 calcolato sulla sequenza di byte grezzi ricevuta nel body HTTP (`payload_body`), cifrata con la chiave segreta condivisa (`secret_token.encode('utf-8')`).
2. **Formato Prefisso Rigoroso**: Esige tassativamente il prefisso `sha256=` seguito dalla stringa esadecimale a 64 caratteri in formato minuscolo generata da `.hexdigest()`. Qualsiasi variazione (prefissi mancanti, algoritmi differenti come `sha1=`, caratteri maiuscoli) restituisce `False`.
3. **Resistenza ai Timing Attack**: Il confronto non avviene tramite il classico operatore di uguaglianza (`==`), il quale si interromperebbe al primo carattere differente aprendo la porta ad attacchi di analisi temporale (side-channel timing attacks). Viene invece utilizzato rigorosamente **`hmac.compare_digest`**, che garantisce un confronto in tempo costante indipendente dal numero di byte corrispondenti.
4. **Resilienza alle Eccezioni**: Intercetta `TypeError` e `UnicodeError`, neutralizzando payload anomali o tentativi di injection con stringhe malformate nel contesto degli header HTTP.

### 2.4 Motore di Esecuzione (`src/executor.py`)
L'esecuzione operativa è demandata a due funzioni:
```python
def run_command(command: list[str], cwd: str) -> bool:
def deploy(repo_path: str) -> bool:
```

#### Prevenzione della Command Injection
I comandi di sistema non vengono mai invocati assemblando stringhe arbitrarie interpretate da una shell di sistema (ovvero `shell=True` è bandito). Ciascun comando è strutturato come lista di token (`list[str]`) ed eseguito tramite:
```python
subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
```
In questo modo, il sistema operativo invoca direttamente l'eseguibile binario (`git` o `docker`), passando gli argomenti come array di parametri ed escludendo qualsiasi possibilità di concatenazione di comandi dannosi (tramite caratteri speciali come `;`, `&&`, `|` o backtick).

#### Pipeline Sequenziale Rigida (Short-Circuiting)
La funzione `deploy(repo_path)` esegue tre passaggi deterministici in sequenza all'interno della directory specificata (`cwd=repo_path`):
1. **Fase 1: Sincronizzazione Sorgente**:
   `["git", "pull", "origin", "main"]`
   Scarica i commit più recenti dal branch `main` del remote `origin`. Se il comando restituisce un codice di uscita diverso da 0 (es. conflitti di merge, errori di rete Git, remote irraggiungibile), la pipeline si arresta immediatamente registrando l'errore e ritornando `False`.
2. **Fase 2: Download Immagini Container**:
   `["docker", "compose", "pull"]`
   Effettua il pull preventivo delle nuove versioni delle immagini specificate nel file `docker-compose.yml`. Se il registry Docker è irraggiungibile o l'autenticazione fallisce, la procedura si arresta senza toccare i container in esecuzione.
3. **Fase 3: Ricreazione ed Avvio Container**:
   `["docker", "compose", "up", "-d"]`
   Riavvia e ricrea solo i container le cui immagini o configurazioni sono cambiate, eseguendoli in modalità detached (`-d`). Se questa fase si conclude con successo, la funzione restituisce `True`.

### 2.5 Dispatcher Notifiche ed Isolamento dei Provider (`src/notifier.py`)
Il modulo `src/notifier.py` orchestra l'invio delle notifiche sullo stato del deployment:
- Supporta Telegram (mediante l'API Bot ufficiale) e n8n (mediante chiamata HTTP POST verso Webhook in entrata).
- **Fault Isolation (Isolamento dei Guasti)**: Ciascun canale di notifica è incapsulato in un blocco `try...except` indipendente. Se Telegram è offline, va in timeout o risponde con errore 400/500, n8n viene comunque eseguito regolarmente, e viceversa.
- **Protezione dell'Endpoint Principale**: In `src/main.py:62-65`, l'invocazione di `notify()` è racchiusa in un ulteriore blocco protettivo generale: eventuali anomalie impreviste nel sistema di notifica vengono loggate ma non fanno mai fallire la risposta HTTP destinata al client Git.

---

## 3. Ciclo di Vita della Richiesta Webhook e Gestione HTTP

Quando una richiesta HTTP giunge all'endpoint `POST /webhook`, attraversa le seguenti fasi logiche:

```
[Richiesta in ingresso]
          │
          ▼
Controllo Chiave Segreta
├── Segreto assente o stringa vuota ──► HTTP 401 Unauthorized
└── Segreto configurato
          │
          ▼
Estrazione Header X-Hub-Signature-256
├── Header assente o vuoto ──────────► HTTP 401 Unauthorized
└── Header presente
          │
          ▼
Verifica Crittografica (HMAC-SHA256)
├── Firma non corrispondente ────────► HTTP 401 Unauthorized
└── Firma valida
          │
          ▼
Esecuzione Pipeline Deploy (deploy(repo_path))
├── git pull origin main
├── docker compose pull
└── docker compose up -d
          │
          ▼
Spedizione Notifiche (notify(status, repo_path, config))
├── Invio a Telegram (se attivo)
└── Invio a n8n (se attivo)
          │
          ▼
Risposta HTTP al Provider Git ───────► HTTP 200 OK
                                       {"status": "success"|"failed",
                                        "deployed": true|false}
```

### Rationale del Codice HTTP 200 in Caso di Deploy Fallito

Una decisione architetturale fondamentale di GitOps Auto-Deployer è la seguente:
> **Se la firma crittografica HMAC è valida ma la procedura di deploy fallisce (ad esempio errore durante `git pull` o `docker compose pull`), l'endpoint `/webhook` restituisce comunque un codice `HTTP 200 OK` con payload `{"status": "failed", "deployed": false}`.**

#### Motivazione Tecnica: Prevenzione dei Webhook Retry Storm
1. **Comportamento dei Provider Git (GitHub, Gitea, GitLab)**:
   I provider Git considerano qualsiasi risposta con codice `4xx` o `5xx` come un errore di trasmissione di rete o un fallimento del server ricevente. In base a questo, attivano politiche aggressive di *exponential backoff retry*, ritentando l'invio dello stesso webhook più volte nell'arco di diverse ore.
2. **Effetto Valanga (Retry Storm)**:
   Se un comando Git fallisce a causa di una configurazione errata sul server (ad es. un conflitto di branch o una chiave di deploy scaduta), rispondere con `HTTP 500` indurrebbe il provider Git a ritentare continuamente la richiesta. Questo innescherebbe un ciclo continuo di esecuzioni fallite, sovraccaricando la CPU dell'host, intasando i log e moltiplicando le notifiche di errore.
3. **Semantica del Protocollo**:
   Dal punto di vista dell'infrastruttura di ricezione webhook, la transazione HTTP ha avuto pieno successo: il server era online, la richiesta era legittima, la firma crittografica è stata verificata e l'evento è stato preso in carico. Il fallimento del task interno è un dato applicativo, non un errore di trasporto. Il fallimento viene prontamente segnalato agli sviluppatori tramite i canali di notifica dedicati (Telegram e n8n) e registrato nei log di sistema.

---

## 4. Tabella di Riferimento degli Endpoint e Codici HTTP

| Endpoint | Metodo | Scenario Operativo | Status Code | Risposta JSON | Comportamento Interno |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/health` | `GET` | Probe di monitoraggio o healthcheck Docker | `200 OK` | `{"status": "ok"}` | Risposta immediata di stato del servizio. |
| `/health` | `POST`, `PUT`, `DELETE` | Metodo HTTP non consentito | `405 Method Not Allowed` | `{"detail": "Method Not Allowed"}` | Rifiuto gestito automaticamente dal router FastAPI. |
| `/webhook` | `POST` | Firma HMAC valida, pipeline di deploy completata con successo | `200 OK` | `{"status": "success", "deployed": true}` | Tutti e 3 i comandi eseguiti con successo. Notifiche inviate. |
| `/webhook` | `POST` | Firma HMAC valida, ma fallimento durante `git` o `docker compose` | `200 OK` | `{"status": "failed", "deployed": false}` | Interruzione immediata della pipeline. Notifiche di errore inviate. Prevenzione retry storm. |
| `/webhook` | `POST` | Header `X-Hub-Signature-256` assente | `401 Unauthorized` | `{"detail": "Invalid signature"}` | Richiesta scartata prima di qualsiasi elaborazione. |
| `/webhook` | `POST` | Firma HMAC errata o digest corrotto/manomesso | `401 Unauthorized` | `{"detail": "Invalid signature"}` | Protezione contro attacchi di manomissione o spoofing. |
| `/webhook` | `POST` | Header firma privo del prefisso `sha256=` o malformato | `401 Unauthorized` | `{"detail": "Invalid signature"}` | Scartato dal controllo del prefisso in `security.py`. |
| `/webhook` | `POST` | Chiave `webhook.secret` non configurata o stringa vuota | `401 Unauthorized` | `{"detail": "Invalid signature"}` | Il server rifiuta per sicurezza operativa ogni deploy se privo di secret. |
| `/webhook` | `GET`, `PUT`, `DELETE`, `PATCH` | Metodo non consentito su endpoint webhook | `405 Method Not Allowed` | `{"detail": "Method Not Allowed"}` | Protezione router FastAPI. |
| Qualsiasi | Qualsiasi | Percorso inesistente (es. `/`, `/api`, `/deploy`) | `404 Not Found` | `{"detail": "Not Found"}` | Gestore standard 404. |
| `/webhook` | `POST` | Crash non gestito a livello applicativo | `500 Internal Server Error` | `{"detail": "Internal Server Error"}` | Riservato solo ad anomalie fatali non previste del framework. |

---

## 5. Considerazioni di Concorrenza e Threading

Nell'implementazione corrente:
1. `src/executor.py` esegue comandi bloccanti in modo sincrono tramite `subprocess.run`.
2. Durante l'esecuzione di `git pull origin main`, il file system crea temporaneamente un file di lock (`.git/index.lock`).
3. Se venissero elaborati più webhook contemporaneamente da più processi worker paralleli, potrebbero verificarsi conflitti di accesso concorrente su Git.
4. Per questa ragione, l'architettura raccomanda categoricamente l'esecuzione del server Uvicorn con un singolo worker di processo (`--workers 1`), garantendo l'elaborazione serializzata e deterministica degli eventi di aggiornamento.
