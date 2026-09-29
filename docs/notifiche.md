# Guida Completa alle Notifiche (Telegram & n8n)

Il microservizio **GitOps Auto-Deployer** include un motore di notifica multicanale implementato in `src/notifier.py`. Al termine dell'esecuzione della pipeline di deployment, il sistema è in grado di inviare alert dettagliati in tempo reale sullo stato dell'operazione.

I due canali attualmente supportati e integrati nativamente sono:
1. **Telegram**: messaggistica istantanea tramite l'API ufficiale dei Bot di Telegram, con rendering visuale formattato in HTML ed emoji dinamiche.
2. **n8n**: integrazione con piattaforme di automazione e workflow low-code tramite richieste HTTP POST strutturate verso un nodo Webhook in entrata.

Questo documento illustra la configurazione operativa, gli schemi dei dati, i template grafici e il principio architetturale di isolamento dei guasti.

---

## 1. Configurazione del Canale Telegram

La funzione incaricata dell'invio dei messaggi è:
```python
send_telegram_notification(bot_token: str, chat_id: str, message: str) -> bool
```

### 1.1 Creazione del Bot con @BotFather
Per poter inviare notifiche a utenti, gruppi o canali, è necessario creare un Bot Telegram:
1. Apri Telegram e cerca l'account ufficiale [**@BotFather**](https://t.me/BotFather).
2. Avvia la chat cliccando su **Avvia** (o invia il comando `/start`).
3. Invia il comando `/newbot` e segui le istruzioni:
   - Assegna un nome amichevole al bot (es. `GitOps Deployer Bot`).
   - Scegli un username univoco che termini con `bot` (es. `my_gitops_deployer_bot`).
4. `@BotFather` risponderà rilasciando il **Token HTTP API** (ad esempio `7123456789:AAFlM3j0XYZabc1234567890abcdefghijk`).
5. Copia questo valore: corrisponde a `notifications.telegram.bot_token` (oppure alla variabile d'ambiente `TELEGRAM_BOT_TOKEN`).

---

### 1.2 Come Ottenere il `chat_id` di Destinazione

Il bot deve conoscere l'ID numerico della chat a cui inviare i messaggi. È possibile inviare notifiche a un account personale, a un gruppo o a un canale.

#### Metodo A: Notifiche a una Chat Personale (Utente Singolo)
1. Cerca su Telegram il bot [**@userinfobot**](https://t.me/userinfobot) e clicca su **Avvia**.
2. Il bot risponderà con le tue informazioni, tra cui `Id: 123456789`. Questo numero è il tuo `chat_id`.
3. **Passo Fondamentale**: apri la chat con il tuo nuovo bot (creato al punto 1.1) e clicca su **Avvia** (`/start`). Se non avvii la chat con il bot, Telegram impedirà al bot di inviarti messaggi per ragioni anti-spam.

#### Metodo B: Notifiche a un Gruppo o Canale Telegram
1. Crea un gruppo o canale (es. *Team DevOps Alerts*) e aggiungi il tuo bot come membro (o come amministratore con permesso di pubblicazione se si tratta di un canale).
2. Invia un messaggio di prova nel gruppo (es. `test`).
3. Apri il browser o usa `curl` per interrogare l'API `getUpdates` di Telegram sostituendo il tuo token:
   ```bash
   curl -s "https://api.telegram.org/bot<TUO_BOT_TOKEN>/getUpdates"
   ```
4. Nella risposta JSON individua l'oggetto `"chat"`:
   ```json
   "chat": {
     "id": -1001234567890,
     "title": "Team DevOps Alerts",
     "type": "supergroup"
   }
   ```
5. Il valore `-1001234567890` (compreso il segno meno) è il `chat_id` da inserire nella configurazione.

---

### 1.3 Template dei Messaggi e Sanitizzazione HTML

I messaggi Telegram vengono formattati con `parse_mode: "HTML"`.

#### Protezione da HTML Injection
Tutti i valori variabili incorporati nel messaggio (`status`, `repo_path`, `details`) vengono preventivamente sanificati mediante la libreria standard `html.escape()` di Python (`src/notifier.py:98-105`). Questo impedisce che percorsi file o messaggi d'errore contenenti caratteri come `<`, `>`, o `&` possano rompere il rendering dei tag HTML o causare errori di parsing su Telegram.

#### Template di Esito Positivo (Deploy Completato con Successo)
```html
🚀 <b>GitOps Deployment SUCCESS</b>
<b>Repository:</b> <code>/opt/deployments/production-app</code>
```
Se sono stati passati dettagli opzionali (`details`), viene aggiunta una riga finale:
```html
<b>Details:</b> Aggiornamento completato con successo
```

#### Template di Esito Negativo (Deploy Fallito)
```html
❌ <b>GitOps Deployment FAILED</b>
<b>Repository:</b> <code>/opt/deployments/production-app</code>
<b>Details:</b> Errore nell'esecuzione del comando: git pull origin main
```

---

## 2. Configurazione del Canale n8n

La funzione incaricata della notifica verso n8n è:
```python
send_n8n_notification(webhook_url: str, payload: dict) -> bool
```

### 2.1 Configurazione del Nodo Webhook in n8n
Per ricevere gli eventi di deployment all'interno di n8n:
1. Crea un nuovo Workflow in n8n (oppure aprine uno esistente).
2. Aggiungi un nodo di tipo **Webhook**:
   - **HTTP Method**: Seleziona **`POST`**.
   - **Path**: Inserisci un percorso identificativo (es. `gitops-deploy`).
   - **Response Mode**: Seleziona *Respond Immediately* oppure *Using 'Respond to Webhook' Node*.
   - **Response Code**: `200` (n8n può rispondere con qualsiasi codice nel range $200 \le \text{code} < 300$).
3. Copia l'URL del Webhook (usa il *Test URL* durante la configurazione o il *Production URL* dopo aver attivato il workflow).
4. Inserisci l'URL nel file `config.yaml` sotto `notifications.n8n.webhook_url` oppure nella variabile d'ambiente `N8N_WEBHOOK_URL`.

---

### 2.2 Schema JSON del Payload Inviato a n8n

Il modulo `src/notifier.py` serializza un oggetto JSON deterministico e strutturato, ideale per essere elaborato da nodi successivi (es. filtri IF, integrazioni verso Slack, Discord, Microsoft Teams, Jira o database SQL/NoSQL).

#### Schema Ufficiale del Payload
```json
{
  "event": "deployment",
  "status": "success",
  "repo_path": "/opt/deployments/production-app",
  "message": "Deployment succeeded",
  "details": "",
  "timestamp": "2026-09-28T19:05:00.123456+00:00"
}
```

In caso di fallimento della pipeline:
```json
{
  "event": "deployment",
  "status": "failure",
  "repo_path": "/opt/deployments/production-app",
  "message": "Deployment failed: Errore durante docker compose pull",
  "details": "Errore durante docker compose pull",
  "timestamp": "2026-09-28T19:05:00.123456+00:00"
}
```

#### Descrizione Dettagliata dei Campi

| Proprietà JSON | Tipo Dato | Descrizione | Note e Valori |
| :--- | :--- | :--- | :--- |
| `event` | `string` | Identificativo univoco dell'evento generato | Valore fisso `"deployment"`. Consente a n8n di gestire eventi eterogenei sullo stesso webhook. |
| `status` | `string` | Esito dell'operazione di deployment | `"success"` se la pipeline si è conclusa con successo (`status == True`), altrimenti `"failure"`. |
| `repo_path` | `string` | Percorso locale del repository aggiornato | Stringa corrispondente a `deploy.repo_path`. |
| `message` | `string` | Messaggio descrittivo leggibile | `"Deployment succeeded"` oppure `"Deployment failed"` (con concatenazione di `: <details>` se forniti). |
| `details` | `string` | Dettagli opzionali o output di errore | Stringa contenente eventuali messaggi diagnostici (default `""`). |
| `timestamp` | `string` | Data e ora dell'evento in UTC | Timestamp formattato secondo lo standard ISO 8601 UTC generato tramite `datetime.now(timezone.utc).isoformat()`. |

---

### 2.3 Esempio di Workflow n8n per Notifiche Multi-Piattaforma

Grazie alla struttura pulita del JSON inviato, un tipico workflow n8n può facilmente smistare l'evento:
1. **Nodo Webhook**: Riceve la richiesta `POST`.
2. **Nodo Switch / IF**: Valuta il campo `{{ $json.body.status }}`:
   - Se uguale a `"success"`, invia una card su Microsoft Teams / Slack sul canale `#deploys`.
   - Se uguale a `"failure"`, invia un alert ad alta priorità su PagerDuty / Opsgenie e crea un issue su GitLab/GitHub.
3. **Nodo Postgres / Google Sheets**: Registra data, ora, repository ed esito nel registro di audit dei rilasci.

---

## 3. Selezione e Attivazione dei Canali (`active_targets`)

L'attivazione dei canali di notifica è controllata dalla lista `active_targets`.

### Tramite `config.yaml`
```yaml
notifications:
  active_targets:
    - "telegram"
    - "n8n"
```
È possibile specificare solo uno dei due canali (es. solo Telegram o solo n8n), oppure impostare una lista vuota `[]` per disattivare qualsiasi notifica esterna.

### Tramite Variabile d'Ambiente `ACTIVE_TARGETS`
Il sistema gestisce in modo intelligente la variabile d'ambiente:
- **Formato Array JSON**: `ACTIVE_TARGETS='["telegram", "n8n"]'` o `ACTIVE_TARGETS='["telegram"]'`
- **Formato Separato da Virgole**: `ACTIVE_TARGETS=telegram,n8n` o `ACTIVE_TARGETS=n8n`

I nomi dei target vengono normalizzati automaticamente: gli spazi iniziali e finali vengono rimossi e i caratteri vengono convertiti in minuscolo (`str(t).strip().lower()`), rendendo valide espressioni come `Telegram, N8N` o `[ "telegram" ]`.

---

## 4. Architettura di Isolamento dei Guasti (Fault Isolation)

Una delle caratteristiche di robustezza fondamentali di GitOps Auto-Deployer è l'**isolamento categorico tra sottosistemi**:

```
                  notify(...)
                       │
       +---------------+---------------+
       |                               |
       ▼                               ▼
[Blocco try...except]          [Blocco try...except]
  Invio a Telegram                Invio a n8n
       │                               │
  (Se crasha/timeout)            (Se crasha/timeout)
       │                               │
       ▼                               ▼
outcomes["telegram"]=False     outcomes["n8n"]=False
       │                               │
       +---------------+---------------+
                       │
                       ▼
             outcomes completati
                       │
                       ▼
       Ritorno a src/main.py:handle_webhook
       (Blocco try...except protettivo)
                       │
                       ▼
               HTTP 200 OK inviato
           (Nessun crash 500 al client Git)
```

1. **Timeout HTTP Esplicito**: Sia la chiamata a Telegram che quella a n8n utilizzano il client `httpx` configurato con un timeout massimo rigido di `10.0` secondi. Un rallentamento o blocco di rete verso i server di Telegram o n8n non lascerà mai il processo orfano o bloccato indefinitamente.
2. **Indipendenza tra Provider**: La chiamata verso Telegram è racchiusa in un blocco `try...except`. Se le API di Telegram restituiscono un errore HTTP (es. bot bloccato `403` o token non valido `401`) o la connessione scade, l'errore viene intercettato e registrato nel log, e il codice procede immediatamente all'invio della notifica a n8n.
3. **Immunità dell'Endpoint Webhook**: L'invocazione di `notify()` all'interno del gestore della richiesta `src/main.py:62-66` è protetta da un ulteriore blocco `try...except Exception as e`. Anche qualora l'intero sottosistema di notifica dovesse fallire in modo catastrofico (ad es. per mancanza totale di connettività Internet sull'host), il webhook restituirà comunque la corretta risposta `HTTP 200 OK` al provider Git, evitando retry storm e conservando i log di esecuzione sull'host.
