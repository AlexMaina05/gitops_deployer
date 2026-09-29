# ✅ Checklist Pre-Deploy — Credenziali e Dati Necessari

Questo documento elenca **tutto ciò che devi raccogliere o preparare** prima di poter configurare e avviare GitOps Auto-Deployer. Segui l'ordine dall'alto in basso: ogni sezione ti dice dove trovare la credenziale e dove inserirla nel file `config.yaml`.

---

## 1. 🖥️ Il Tuo Server (VM Linux)

Prima di tutto, assicurati di avere accesso al server su cui gira Docker.

| Dato | Dove trovarlo | Dove usarlo |
|:-----|:-------------|:------------|
| **IP pubblico del server** (o dominio) | Pannello del tuo VPS provider (es. Hetzner, DigitalOcean, Netcup) → sezione "Server" | Da inserire come **Payload URL** sul provider Git (vedi sezione 4) |
| **Porta esposta** | Predefinita: `8000` (diretta) oppure `443` se usi un Reverse Proxy HTTPS | Stessa destinazione del Payload URL |
| **Percorso assoluto del repository** | Esegui `pwd` dentro la cartella del progetto sul server, es. `/opt/deployments/mia-app` | Campo `deploy.repo_path` in `config.yaml` |

> [!IMPORTANT]
> La cartella indicata in `deploy.repo_path` deve contenere il file `docker-compose.yml` del tuo progetto target. È la directory su cui verranno eseguiti `git pull` e `docker compose up -d`.

---

## 2. 🔑 Il Webhook Secret (HMAC)

Questo è il segreto condiviso tra il tuo server e il provider Git (GitHub, Gitea, ecc.). Lo **generi tu** e lo inserisci in entrambi i posti.

**Come generarlo** (scegli uno dei metodi):

```bash
# Metodo 1 — Linux/macOS (genera 32 byte casuali in esadecimale)
openssl rand -hex 32

# Metodo 2 — Python
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Output di esempio:
```
a7f3c91e2d084b6e5f1a4c8d9b0e2f3a4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9
```

| Dato | Dove inserirlo |
|:-----|:--------------|
| La stringa generata | `config.yaml` → campo `webhook.secret` |
| La **stessa** stringa generata | Impostazioni Webhook del provider Git → campo **"Secret"** (vedi sezione 4) |

> [!CAUTION]
> Non committare mai il `config.yaml` con il secret su Git. Il file `.gitignore` del progetto lo esclude già automaticamente.

---

## 3. 📬 Notifiche — Scegli il tuo canale

Puoi usare **Telegram**, **n8n**, entrambi, o nessuno. Raccogli le credenziali solo per i canali che vuoi attivare.

### 3.1 🤖 Telegram

Dovrai creare un Bot Telegram e trovare il tuo Chat ID.

**Passo 1 — Crea il Bot e ottieni il `bot_token`:**
1. Apri Telegram e cerca il contatto **`@BotFather`**.
2. Invia il comando `/newbot`.
3. Scegli un nome (es. `GitOps Deployer`) e uno username univoco che finisce in `bot` (es. `mioserver_gitops_bot`).
4. BotFather risponderà con una stringa del tipo:
   ```
   Done! Use this token to access the HTTP API:
   1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   ```
   ➡️ **Copia questa stringa**: è il tuo `bot_token`.

**Passo 2 — Trova il tuo `chat_id`:**
1. Cerca il bot appena creato su Telegram e invia un qualsiasi messaggio (es. "ciao").
2. Apri il seguente URL nel browser, sostituendo `<TOKEN>` con il token appena ottenuto:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Cerca nel JSON il campo `"chat"` → `"id"`. Esempio:
   ```json
   {"ok":true,"result":[{"message":{"chat":{"id":123456789}}}]}
   ```
   ➡️ **Copia il numero**: è il tuo `chat_id` (può essere negativo se è un gruppo).

| Dato | Dove inserirlo in `config.yaml` |
|:-----|:-------------------------------|
| `bot_token` (es. `1234567890:AAH...`) | `notifications.telegram.bot_token` |
| `chat_id` (es. `123456789`) | `notifications.telegram.chat_id` |

---

### 3.2 🔄 n8n

Dovrai avere un'istanza n8n raggiungibile dal tuo server e creare un Workflow con un nodo Webhook.

**Passo 1 — Crea il Workflow in n8n:**
1. Apri la tua istanza n8n (es. `https://n8n.tuodominio.it`).
2. Crea un nuovo **Workflow**.
3. Aggiungi un nodo **Webhook** come trigger.
4. Imposta il metodo su **POST** e il percorso come preferisci (es. `/gitops-deploy`).
5. Copia l'**URL di produzione** del webhook. Avrà la forma:
   ```
   https://n8n.tuodominio.it/webhook/gitops-deploy
   ```

**Passo 2 — Aggiungi la logica (esempi di nodi successivi):**
- Nodo **IF**: controlla se `{{ $json.status }}` è `"success"` o `"failure"`.
- Nodo **Send Email** / **Telegram** / **Slack** per notifica finale.

**Il payload JSON che il deployer invia ad n8n:**
```json
{
  "event": "deployment",
  "status": "success",
  "repo_path": "/opt/deployments/mia-app",
  "message": "Deployment succeeded",
  "details": "",
  "timestamp": "2026-09-28T19:00:00+00:00"
}
```

| Dato | Dove inserirlo in `config.yaml` |
|:-----|:-------------------------------|
| URL di produzione del nodo Webhook n8n | `notifications.n8n.webhook_url` |

---

## 4. 🐙 Provider Git — Configurazione del Webhook

Una volta che il server è in ascolto, devi dire al tuo provider Git dove mandare le notifiche di push.

### 4.1 GitHub

Vai su: `Repository` → `Settings` → `Webhooks` → **Add webhook**

| Campo | Valore da inserire |
|:------|:-------------------|
| **Payload URL** | `https://deploy.tuodominio.it/webhook` oppure `http://<IP_SERVER>:8000/webhook` |
| **Content type** | `application/json` *(obbligatorio)* |
| **Secret** | La stringa generata al passo 2 (deve coincidere con `webhook.secret`) |
| **SSL verification** | ✅ Enable (in produzione con HTTPS) |
| **Which events** | ✅ Just the **push** event |
| **Active** | ✅ Spuntato |

### 4.2 Gitea / Forgejo

Vai su: `Repository` → `Impostazioni` → `Webhooks` → **Aggiungi Webhook**

> [!WARNING]
> Seleziona il tipo **"GitHub"** (non "Gitea nativo"). Solo il tipo GitHub invia l'header `X-Hub-Signature-256` richiesto dal deployer.

| Campo | Valore da inserire |
|:------|:-------------------|
| **URL di destinazione** | `https://deploy.tuodominio.it/webhook` |
| **POST Content Type** | `application/json` |
| **Segreto** | La stringa generata al passo 2 |
| **Attivatori** | ✅ Push Events |
| **Attivo** | ✅ Spuntato |

---

## 5. 📋 `config.yaml` Finale — Template Pronto da Compilare

Copia questo template nel file `config.yaml` nella root del progetto e sostituisci i valori tra `< >`:

```yaml
webhook:
  secret: "<STRINGA_SEGRETA_GENERATA_AL_PASSO_2>"

deploy:
  repo_path: "<PERCORSO_ASSOLUTO_REPO_SUL_SERVER>"  # es. /opt/deployments/mia-app

notifications:
  active_targets:
    - "telegram"   # Rimuovi questa riga se non usi Telegram
    - "n8n"        # Rimuovi questa riga se non usi n8n

  telegram:
    bot_token: "<TOKEN_DA_BOTFATHER>"
    chat_id: "<CHAT_ID_NUMERICO>"

  n8n:
    webhook_url: "<URL_WEBHOOK_N8N>"
```

---

## 6. ✅ Checklist Finale

Usa questa lista come verifica prima di avviare il server:

- [ ] **Server pronto**: IP/dominio noto, Docker e Git installati, utente nel gruppo `docker`
- [ ] **`repo_path` corretto**: la cartella esiste sul server e contiene `docker-compose.yml`
- [ ] **Webhook secret generato**: salvato in `config.yaml` → `webhook.secret`
- [ ] **Telegram**: `bot_token` e `chat_id` ottenuti e inseriti in `config.yaml`
- [ ] **n8n**: URL webhook creato e inserito in `config.yaml`
- [ ] **Provider Git configurato**: Payload URL, Content-Type `application/json`, Secret inserito
- [ ] **`config.yaml` NON committato su Git** (verificare con `git status`)
- [ ] **Server raggiungibile**: `curl http://<IP>:8000/health` risponde `{"status":"ok"}`
