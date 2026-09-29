# Integrazione Webhook Git e Specifica Crittografica HMAC

Il microservizio **GitOps Auto-Deployer** adotta un modello di sicurezza *Zero-Trust*: ogni richiesta inviata all'endpoint `/webhook` deve essere autenticata e verificata mediante una firma crittografica **HMAC-SHA256** contenuta nell'header HTTP `X-Hub-Signature-256`.

Questa guida descrive in dettaglio:
1. Le specifiche crittografiche dell'algoritmo di validazione.
2. La configurazione passo-passo sui principali provider Git (**GitHub**, **Gitea/Forgejo**, **GitLab**).
3. Script e comandi pratici per simulare e collaudare webhook sia da terminale Bash che tramite Python.

---

## 1. Specifica Crittografica (HMAC-SHA256)

L'autenticazione è implementata nel modulo `src/security.py` mediante la funzione `verify_github_signature`:

```python
def verify_github_signature(payload_body: bytes, secret_token: str, signature_header: str) -> bool
```

### 1.1 Parametri Crittografici Fondamentali

| Parametro | Specifica Tecnica | Regole di Convalida |
| :--- | :--- | :--- |
| **Algoritmo di Hashing** | HMAC-SHA256 | Basato sulla funzione di hash crittografico SHA-256 a 256 bit (`hashlib.sha256`). |
| **Header HTTP Richiesto** | `X-Hub-Signature-256` | Header standard de-facto introdotto da GitHub. La sua assenza comporta l'immediata restituzione di `HTTP 401 Unauthorized`. |
| **Prefisso Obbligatorio** | `sha256=` | L'header deve tassativamente iniziare con la stringa esatta in caratteri minuscoli `sha256=`. Prefissi come `SHA256=`, `sha-256=` o la stringa esadecimale priva di prefisso vengono scartati. |
| **Formato del Digest** | Esadecimale a 64 caratteri minuscoli | Generato tramite il metodo `.hexdigest()` di Python. Lunghezza totale dell'header: esattamente 71 caratteri (`7` caratteri di prefisso + `64` caratteri hex). |
| **Corpo del Messaggio (Payload)** | Sequenza binaria grezza (`bytes`) | L'hash deve essere calcolato sull'esatto flusso di byte grezzi inviato dal client (`await request.body()`). Qualsiasi operazione preliminare di deserializzazione o riformattazione JSON altererebbe i byte, invalidando la firma. |
| **Codifica del Secret Token** | Byte codificati in UTF-8 | `secret_token.encode('utf-8')`. |
| **Protezione Timing Attack** | `hmac.compare_digest` | La comparazione tra la firma attesa e quella ricevuta avviene in tempo costante per neutralizzare gli attacchi di tipo side-channel basati sui tempi di risposta. |

---

## 2. Configurazione dei Provider Git

### 2.1 Configurazione su GitHub (Nativo 100%)

GitHub supporta nativamente la firma crittografica `X-Hub-Signature-256`.

1. Apri il tuo repository su **GitHub**.
2. Clicca su **Settings** (in alto a destra), quindi seleziona **Webhooks** dal menu laterale sinistro.
3. Clicca sul pulsante **Add webhook** (potrebbe essere richiesta la conferma della password o 2FA).
4. Compila i campi del modulo come segue:
   - **Payload URL**: `https://deploy.tuodominio.it/webhook` (o `http://<IP_SERVER>:8000/webhook` se in ambiente di test).
   - **Content type**: Seleziona categoricamente **`application/json`** *(Attenzione: NON selezionare `application/x-www-form-urlencoded`)*.
   - **Secret**: Inserisci l'esatta chiave segreta configurata in `config.yaml` (`webhook.secret`) o nella variabile d'ambiente `WEBHOOK_SECRET`.
   - **SSL verification**: Lascia selezionato **Enable SSL verification** (fondamentale in ambienti di produzione con HTTPS).
   - **Which events would you like to trigger this webhook?**: Seleziona **"Just the push event"** (il deployer ascolta gli eventi di rilascio).
   - **Active**: Assicurati che la casella di controllo sia spuntata.
5. Clicca su **Add webhook**.
6. GitHub invierà immediatamente un evento di test denominato `ping`. Verifica che nella sezione *Recent Deliveries* compaia una spunta verde con codice di risposta **200 OK**.

---

### 2.2 Configurazione su Gitea e Forgejo (Modalità Compatibile GitHub)

Gitea e Forgejo supportano la firma crittografica standard di GitHub, a condizione di selezionare il tipo corretto di webhook.

1. Accedi alla dashboard del tuo repository su **Gitea** o **Forgejo**.
2. Vai su **Impostazioni (Settings)** $\rightarrow$ **Webhooks**.
3. Clicca su **Aggiungi Webhook (Add Webhook)**.
4. **IMPORTANTE - Scelta della Tipologia**:  
   Seleziona la tipologia **GitHub** dall'elenco a discesa.  
   *(Nota bene: Non selezionare il tipo "Gitea". Il tipo nativo di Gitea invia l'header proprietario `X-Gitea-Signature` con hash grezzo, mentre selezionando la modalità "GitHub" invierà lo standard `X-Hub-Signature-256: sha256=<hex>` perfettamente compreso dal nostro microservizio)*.
5. Configura i parametri:
   - **URL di destinazione (Target URL)**: `https://deploy.tuodominio.it/webhook`
   - **Metodo HTTP**: `POST`
   - **POST Content Type**: `application/json`
   - **Segreto (Secret)**: Inserisci il token segreto condiviso.
   - **Attivatori di eventi (Trigger On)**: Seleziona **Eventi di push (Push Events)**.
   - **Attivo (Active)**: Casella spuntata.
6. Clicca su **Aggiungi Webhook**. Invia un evento di test per confermare la corretta ricezione (codice 200).

---

### 2.3 Integrazione con GitLab (Analisi Architetturale e Soluzioni)

#### Perché GitLab non funziona in modo nativo diretto?
GitLab non implementa la firma HMAC-SHA256 calcolata sul corpo della richiesta HTTP. GitLab invia invece un token statico in chiaro nell'header HTTP proprietario denominato **`X-Gitlab-Token`**. 

Poiché `src/main.py` richiede la presenza obbligatoria di `X-Hub-Signature-256` ed esegue la verifica crittografica su payload e secret, l'invio diretto di un webhook da GitLab verrebbe respinto con **`401 Unauthorized (detail: Invalid signature)`**.

Per integrare GitLab con GitOps Auto-Deployer sono disponibili tre soluzioni operative collaudate:

---

#### Soluzione A: Trigger tramite Pipeline GitLab CI/CD (Consigliata)
È possibile sfruttare la pipeline CI/CD nativa di GitLab per generare la firma HMAC al termine dei test e invocare il webhook tramite `curl` ed `openssl`.

Nel repository su GitLab, aggiungi la variabile mascherata `WEBHOOK_SECRET` in **Settings** $\rightarrow$ **CI/CD** $\rightarrow$ **Variables**.

Nel file `.gitlab-ci.yml`:
```yaml
stages:
  - test
  - deploy

deploy_to_production:
  stage: deploy
  image: alpine:latest
  only:
    - main
  before_script:
    - apk add --no-cache curl openssl bash
  script:
    - |
      PAYLOAD='{"ref":"refs/heads/main","event":"push","project":"my-app"}'
      SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | sed 's/^.* //')
      echo "Invio webhook firmato con HMAC-SHA256..."
      curl -f -s -X POST "https://deploy.tuodominio.it/webhook" \
        -H "Content-Type: application/json" \
        -H "X-Hub-Signature-256: sha256=$SIGNATURE" \
        -d "$PAYLOAD"
```

---

#### Soluzione B: Workflow Relay tramite n8n
Poiché n8n è già supportato nel nostro ecosistema:
1. In n8n crea un workflow con un nodo **Webhook** che riceve l'evento da GitLab e verifica il token nell'header `X-Gitlab-Token`.
2. Aggiungi un nodo **Crypto** (o nodo *Code* in JavaScript/Python) per generare la firma HMAC-SHA256 sul payload JSON ricevuto usando la chiave segreta.
3. Aggiungi un nodo **HTTP Request** che inoltra la richiesta a `https://deploy.tuodominio.it/webhook` includendo l'header `X-Hub-Signature-256: sha256=<calcolato>`.

---

#### Soluzione C: Firma tramite Reverse Proxy (Nginx + Lua o Caddy)
Se il microservizio è ospitato dietro OpenResty/Nginx con modulo Lua o Caddy, è possibile intercettare le richieste con header `X-Gitlab-Token`, calcolare l'HMAC con le librerie crittografiche del server web e riscrivere l'header in ingresso come `X-Hub-Signature-256` prima di inoltrarlo al processo Uvicorn.

---

## 3. Simulazione e Collaudo Locale dei Webhook

Per testare il corretto funzionamento dell'endpoint senza dover effettuare continuamente push sul repository remoto, è possibile simulare le chiamate webhook in locale.

### 3.1 Script Python di Test (`simulate_webhook.py`)
Crea uno script di utilità per calcolare la firma valida e inviare il payload:

```python
#!/usr/bin/env python3
"""
Script di simulazione per testare l'endpoint /webhook di GitOps Auto-Deployer.
Calcola la corretta firma HMAC-SHA256 e invia un payload JSON fittizio.
"""

import hmac
import hashlib
import json
import requests

# Parametri di configurazione del test
TARGET_URL = "http://127.0.0.1:8000/webhook"
SECRET_TOKEN = "your_webhook_secret_here"  # Deve coincidere con webhook.secret

# Corpo del messaggio (Payload JSON di esempio)
payload_dict = {
    "ref": "refs/heads/main",
    "repository": {
        "name": "my-app",
        "full_name": "developer/my-app"
    },
    "commits": [
        {
            "id": "1a2b3c4d5e6f7g8h9i0j",
            "message": "feat: release new container version"
        }
    ]
}

# Serializzazione in formato binario UTF-8 compatto
payload_bytes = json.dumps(payload_dict, separators=(',', ':')).encode("utf-8")

# Calcolo della firma HMAC-SHA256
hash_digest = hmac.new(
    SECRET_TOKEN.encode("utf-8"),
    msg=payload_bytes,
    digestmod=hashlib.sha256
).hexdigest()

signature_header = f"sha256={hash_digest}"

print(f"[*] Invio richiesta a: {TARGET_URL}")
print(f"[*] Signature Header: {signature_header}")
print(f"[*] Payload Dimensione: {len(payload_bytes)} bytes")

# Invio richiesta HTTP POST
headers = {
    "Content-Type": "application/json",
    "X-Hub-Signature-256": signature_header
}

try:
    response = requests.post(TARGET_URL, data=payload_bytes, headers=headers, timeout=30)
    print(f"\n[+] Codice di risposta HTTP: {response.status_code}")
    print(f"[+] Corpo della risposta: {response.text}")
except requests.exceptions.RequestException as e:
    print(f"\n[-] Errore di connessione: {e}")
```

---

### 3.2 Simulazione da Terminale Linux / Bash con `curl` e `openssl`

In ambiente Linux o macOS, è possibile generare la firma direttamente dalla riga di comando:

```bash
# 1. Definizione delle variabili
SECRET="your_webhook_secret_here"
PAYLOAD='{"ref":"refs/heads/main","action":"push"}'

# 2. Calcolo della firma esadecimale HMAC-SHA256
SIGNATURE=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $NF}')

# 3. Invio della richiesta HTTP con curl
curl -X POST "http://127.0.0.1:8000/webhook" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=$SIGNATURE" \
  -d "$PAYLOAD"
```

Risposta attesa in caso di successo:
```json
{"status":"success","deployed":true}
```

---

### 3.3 Collaudo del Rifiuto di Firme Non Valide (Test di Sicurezza)

Per verificare che il server respinga correttamente tentativi di manomissione o spoofing, invia una richiesta con firma arbitraria errata:

```bash
curl -i -X POST "http://127.0.0.1:8000/webhook" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=0000000000000000000000000000000000000000000000000000000000000000" \
  -d '{"ref":"refs/heads/main"}'
```

Risposta corretta attesa:
```http
HTTP/1.1 401 Unauthorized
content-length: 30
content-type: application/json

{"detail":"Invalid signature"}
```
Questo test conferma che nessuna esecuzione di comandi locali né invio di notifiche viene avviato se l'autenticazione crittografica fallisce.
