# API Usage — Pathfinder 1E Master DD

Questa guida riassume come usare l'API FastAPI esposta dal progetto, con esempi di richieste e note sui limiti.

## Autenticazione e flag runtime

### Matrice policy accesso (env)

| Variabile | Default | Scope | Effetto operativo |
| --- | --- | --- | --- |
| `API_KEY` | `None` | Endpoint protetti da `require_api_key` | Quando `ALLOW_ANONYMOUS=false`, il client deve inviare `x-api-key` uguale a `API_KEY`. |
| `ALLOW_ANONYMOUS` | `false` | Endpoint applicativi (escluso `/metrics`) | Se `true`, disattiva il controllo `API_KEY` e azzera eventuali fail/backoff per il client corrente. |
| `ALLOW_MODULE_DUMP` | `false` | `GET/POST /modules/{name}` | `false`: blocca dump non testuali (`403`) e serve testo parziale (`206`) con header `X-Content-*`; `true`: consente dump completo, salvo moduli protetti non in whitelist. |
| `METRICS_API_KEY` | `None` | `GET /metrics` | Se impostata, abilita accesso a `/metrics` con `x-api-key`; `API_KEY` rimane accettata come fallback. |
| `METRICS_IP_ALLOWLIST` | stringa vuota | `GET /metrics` | CSV IP consentiti (`client.host` o primo IP `x-forwarded-for`), alternativa alla key per esposizione Prometheus. |

- **Header standard**: `x-api-key: <API_KEY>` quando `ALLOW_ANONYMOUS` è disabilitato.
- **Metriche Prometheus**: se manca una chiave valida e l'IP non è in allowlist, `/metrics` risponde `403`.
- **Output modulare con dump disabilitato**: per `.txt`/`.md` il payload è troncato a 4k con `X-Content-Partial: true`, `X-Content-Partial-Reason: ALLOW_MODULE_DUMP=false`, `X-Content-Served-Bytes`, `X-Content-Remaining-Bytes`, `X-Content-Truncated` e status `206 Partial Content`.

### Security logging policy

- I log di autenticazione non includono mai chiavi/API token in chiaro: gli header sensibili (`x-api-key`, `authorization`, `cookie`, `set-cookie`) sono sempre mascherati.
- Per audit vengono mantenuti solo metadati minimi: `client_ip`, `fail_count`, `route` e `user_agent` in forma redatta.

## Endpoint principali

### `GET /health`
Verifica lo stato dell'API e delle directory configurate. Risposta di esempio:

```json
{
  "status": "ok",
  "directories": {
    "modules": { "status": "ok", "path": "src/modules", "message": null },
    "data": { "status": "ok", "path": "src/data", "message": null }
  }
}
```

In caso di problemi, lo stesso payload include `status: "error"`, campi `message` valorizzati e un array `errors`; l'endpoint risponde con `503 Service Unavailable`.

### `GET /modules`
Elenca i moduli disponibili in `src/modules`.

**Esempio**
```http
GET /modules
x-api-key: ${API_KEY}
```

**Risposta**
```json
[
  { "name": "base_profile.txt", "size_bytes": 12345, "suffix": ".txt" },
  { "name": "minmax_builder.txt", "size_bytes": 6789, "suffix": ".txt" }
]
```

### `GET /modules/{name}/meta`
Restituisce metadati (nome, dimensioni, estensione) senza il contenuto del file.
Se il modulo dichiara un header strutturato (es. `version`, `compatibility`) questi
campi vengono esposti insieme a eventuali note di compatibilità in formato stringa
o dizionario. Per i moduli JSON (es. `tavern_hub.json`) `version`/`compatibility`
vengono letti dal blocco `meta` o dal root dell'oggetto JSON, senza necessità di
front matter.

Esempio di risposta:

```json
{
  "name": "ruling_expert.txt",
  "size_bytes": 12345,
  "suffix": ".txt",
  "version": "3.1-hybrid",
  "compatibility": {
    "core_min": "2.6.7",
    "integrates_with": [
      "MinMax Builder",
      "Documentazione",
      "Taverna NPC",
      "Explain",
      "Archivist"
    ]
  }
}
```

### `GET /modules/taverna_saves/meta`
Restituisce quota e metadati della cartella di servizio `taverna_saves`, inclusi path, `max_files`, slot residui, spazio disco libero e policy di naming/overflow. Quando `ALLOW_MODULE_DUMP=false` il payload espone anche `module_dump_allowed: false` e `partial_dump_notice` per ricordare che i dump testuali sono parziali. Il payload include un campo `remediation` con istruzioni per sbloccare Echo gate sotto soglia (<8.5) ripetendo /grade o usando /refine_npc (in sandbox puoi disattivare temporaneamente Echo con /echo off) e per chiudere i QA CHECK bloccanti eseguendo /self_check, completando Canvas+Ledger e verificando Echo ≥ soglia prima di rilanciare /save_npc o /npc_export.

### `GET /modules/taverna_saves/quota`
Espone solo i numeri di quota/occupazione (`current_files`, `remaining_files`, spazio disco, dimensione totale dei JSON salvati).

### `GET|POST /modules/{name}`
Restituisce il contenuto del modulo o, per `minmax_builder.txt`, uno **stub** di risposta del builder.

Parametri principali:
- `mode` (query/body): `core` o `extended` per il builder; `stub` per forzare la risposta di esempio.
- `stub` (query): boolean per ottenere lo stub del builder.
- `class`, `race`, `archetype` (query): usati nello stub per popolare la build fittizia.
- `body` (POST): opzionale, accetta campi `mode`, `builder_mode`, `race`, `archetype`, `hooks`, ecc.

**Esempio — modulo testuale**
```http
GET /modules/base_profile.txt?mode=extended
x-api-key: ${API_KEY}
```
Risposta: contenuto `.txt` (troncato se `ALLOW_MODULE_DUMP=false`).

**Esempio — stub builder**
```http
POST /modules/minmax_builder.txt?stub=true&class=Fighter&race=Elf&archetype="Lore Warden"
x-api-key: ${API_KEY}
Content-Type: application/json

{ "mode": "extended", "hooks": ["serve l'Ordine"], "sheet_locale": "it-IT" }
```

Risposta JSON semplificata:
```json
{
  "class": "Fighter",
  "mode": "extended",
  "build_state": { "class": "Fighter", "mode": "extended", "race": "Elf", "archetype": "Lore Warden", "step": 1, "step_total": 16, "step_labels": { "1": "Profilo Base", "2": "Razza & Classe", "8": "QA & Export", "16": "Chiusura" } },
  "benchmark": { "meta_tier": "T3", "ruling_badge": "validated", "dpr_snapshot": { "livello_1": { "media": 6, "picco": 9 } } },
  "export": { "sheet_payload": { "classi": [{ "nome": "Fighter", "livelli": 1, "archetipi": ["Lore Warden"] }], "statistiche": { "FOR": 16, "DES": 14 }, "hooks": ["serve l'Ordine"] } },
  "narrative": "Elf Lore Warden pronta/o per il campo, specializzata/o in tattiche da Fighter.",
  "ledger": { "movimenti": [{ "voce": "Equipaggiamento iniziale", "importo": -150 }] },
  "composite": { "build": { "build_state": { "class": "Fighter", "mode": "extended", "race": "Elf", "archetype": "Lore Warden", "step": 1, "step_total": 16, "step_labels": { "1": "Profilo Base" } }, "benchmark": { "meta_tier": "T3" }, "export": { "sheet_payload": { "statistiche": { "FOR": 16, "DES": 14 } } } }, "narrative": "...", "sheet": { "statistiche": { "FOR": 16, "DES": 14 } }, "ledger": { "movimenti": [] } }
}
```

> **Nota sulla validazione**: gli snapshot del builder seguono gli schemi JSON `schemas/build_core.schema.json` e `schemas/build_full_pg.schema.json`. I blocchi `build_state`, `benchmark` e `export` hanno campi espliciti (es. `mode` ∈ {`core`,`extended`,`full-pg`}, `step`/`step_total` numerici e `step_labels` con chiavi numeriche) e il sotto-blocco `composite.build` riutilizza gli stessi riferimenti per mantenere identica struttura e versioni. Nei payload full-PG, `sheet_payload` è obbligatoria sia al livello root sia in `composite.build`, mentre `ledger` accetta sia testi sia movimenti strutturati con `voce`/`importo`.
> Ogni snapshot deve includere la PK logica `build_id`, il campo `reference_catalog_version` allineato al manifest corrente e il blocco di audit `step_audit`; gli stessi obblighi valgono per `composite.build` nei payload full-PG.

#### Versione del catalogo di riferimento

- Il manifest RAW/SRD `data/reference/manifest.json` espone il campo `version` (attualmente `2026.04.03`).
- Tutti i payload di build devono includere `reference_catalog_version` con quel valore; lo stub `/modules/minmax_builder.txt` lo compila automaticamente insieme a `catalog_manifest`.
- Per richieste personalizzate è possibile passare il campo nel body (o farlo inserire dal proprio orchestratore) come nell'esempio:
  ```http
  POST /modules/minmax_builder.txt?stub=true&class=Fighter
  x-api-key: ${API_KEY}
  Content-Type: application/json

  {
    "mode": "extended",
    "reference_catalog_version": "2026.04.03",
    "hooks": ["serve l'Ordine"]
  }
  ```
- Se il campo manca o non coincide con il manifest corrente, la validazione JSON Schema fallisce: lo stub restituisce `500 Stub payload non valido...`, mentre i job di review (`tools/generate_build_db.py`) marcano la build come `invalid` con errore `reference_catalog_version`.

#### Contract versioning

- Il contratto è **bloccante**: `reference_catalog_version` deve combaciare con `data/reference/manifest.json -> version` su tutti i payload build (root e `composite.build`).
- In pipeline, `tools/validate_schemas.py` verifica coerenza tra manifesto, dataset `data/reference/*.json` (path + conteggio `entries`) e versioni dichiarate nei payload build presenti nelle directory candidate (`builds/`, `data/builds/`, `reports/builds/`).
- In caso di mismatch, la pipeline deve terminare con exit code `1` per impedire la promozione di snapshot incoerenti.
- Regola operativa dataset reference: ogni modifica a `data/reference/*.json` richiede nello stesso change set (1) update di `data/reference/manifest.json` e (2) nota esplicita in `CHANGELOG.md`.
- Se non sono presenti payload build nelle directory candidate, il controllo emette warning ma continua a validare manifest + dataset; in CI è consigliato passare `--build-dir <path>` verso gli artifact di build reali.


### `GET /knowledge`
Elenca i file in `src/data` (PDF, markdown di supporto). Non restituisce il contenuto dei manuali Paizo protetti.

### `GET /knowledge/{name}/meta`
Metadati per un singolo asset in `src/data`.

## Errori standard
- `401 Unauthorized`: chiave mancante/non valida quando `ALLOW_ANONYMOUS` è disabilitato o `API_KEY` non è configurata.
- `403 Module download not allowed`: download di asset non testuali bloccato quando `ALLOW_MODULE_DUMP=false`.
- `404 Module not found` / `Knowledge file not found`: path valido ma file assente.
- `400 Invalid module/knowledge path`: path con traversal o formato non supportato.
- `503 Service Unavailable`: directory `modules` o `data` non raggiungibili; anche `/health` riporta `503` in questo caso.
- `500 Stub payload non valido`: solo per `/modules/minmax_builder.txt` se la generazione dello stub fallisce.

## Metriche

L'accesso a `/metrics` è protetto da `require_metrics_access`, che accetta le seguenti credenziali:

- Header `x-api-key` valorizzato con `METRICS_API_KEY`.
- In alternativa, lo stesso header può usare la chiave primaria `API_KEY`.
- Allowlist IP configurabile con `METRICS_IP_ALLOWLIST="1.2.3.4,10.0.0.0"` (valori separati da virgole, senza spazi).

Se la richiesta non include una chiave valida **né** proviene da un IP in allowlist, `/metrics` risponde con `403 Forbidden`.

**Esempi `curl`**

- Accesso con chiave dedicata:
  ```bash
  curl -H "x-api-key: ${METRICS_API_KEY}" https://example.org/metrics
  ```
- Accesso con chiave primaria:
  ```bash
  curl -H "x-api-key: ${API_KEY}" https://example.org/metrics
  ```
- Accesso basato su allowlist IP (nessuna chiave, IP autorizzato):
  ```bash
  curl https://example.org/metrics
  ```

**Output**: testo Prometheus con contatori per richieste totali per endpoint/metodo/status, errori 4xx/5xx, attivazioni del backoff di autenticazione e gauge sullo stato delle directory di configurazione.

> **Nota di sicurezza**: in ambienti pubblici usare sempre `METRICS_API_KEY` (o `API_KEY`) e limitare l'allowlist al minimo necessario; evitare allowlist larghe per prevenire scraping non autorizzato.

## Audit richieste build e backoff

- Ogni payload di build deve includere il blocco `step_audit` con i campi obbligatori: `request_timestamp` (ISO8601), `client_fingerprint_hash` (hash della chiave API o del client), `outcome` (`accepted`/`denied`/`backoff`), `attempt_count` (tentativi consecutivi per quella chiave/IP) e `backoff_reason` (stringa o `null` se non applicato). È consigliato popolare anche `request_ip` per correlare IP pubblici e fingerprint.【F:schemas/build_core.schema.json†L328-L369】
- Gli orchestratori che generano build (anche in modalità stub) devono compilare `step_audit` subito dopo la decisione di accettare/negare la richiesta, usando l'istante di arrivo (`request_timestamp`) e il conteggio tentativi che ha determinato l'eventuale backoff (`AUTH_BACKOFF_THRESHOLD`/`AUTH_BACKOFF_SECONDS`).
- Log locale: appendere una riga JSON a `data/audit/build_events.jsonl` (non versionato; esempio in `data/audit/build_events.sample.jsonl`) per ogni build generata o negata. La riga deve riportare `timestamp`, `client_fingerprint_hash`, `request_ip`, `payload_file` (se salvata), `outcome`, `attempt_count` e `backoff_reason` per garantire tracciabilità e indagini su abusi di chiave/IP.
