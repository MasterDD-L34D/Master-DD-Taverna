# Master-DD-Taverna — Core Repo (API + Prompt Kit)

**Un Master per Pathfinder completo e modulare.**

Questo repository contiene il "cuore" di **Master-DD-Taverna** (ex *Pathfinder 1E Master DD*, nato come GPT) in forma esterna:
- tutti i moduli originali (`base_profile.txt`, `Taverna_NPC.txt`, `minmax_builder.txt`, ecc.)
- una piccola API in Python (FastAPI) che espone i moduli ai client (RAG locale; GPT Actions come integrazione legacy)
- i file di supporto (knowledge pack, template scheda, guide PDF)
- un prompt compatto (integrazione legacy da incollare nel builder dei GPT), che usa questa API invece di includere tutto il base_profile

## Struttura

```text
pathfinder_master_dd_repo/
├─ README.md
├─ requirements.txt
├─ .gitignore
├─ src/
│  ├─ app.py                # FastAPI con endpoint per i moduli
│  ├─ config.py             # Configurazione path e sicurezza base
│  ├─ modules/              # TUTTI i tuoi moduli originali (txt/md/json)
│  └─ data/                 # PDF di supporto (gear guide, crafter guide, ecc.)
├─ gpt/
│  ├─ system_prompt_core.md # Istruzioni compatte da incollare nel GPT
│  └─ openapi.json          # Spec Actions per collegare l'API
└─ docs/
   ├─ architecture.md       # Spiegazione architettura Kernel + moduli
   ├─ api_usage.md          # Endpoint API, parametri, esempi
   └─ module_index.md       # Indice rapido dei file in src/modules
```

Per obiettivi, milestone e decisioni architetturali sulle build/moduli consulta anche la cartella `planning/`:

- [planning/roadmap.md](planning/roadmap.md) raccoglie roadmap e obiettivi aggiornati.
- [planning/decisions.md](planning/decisions.md) contiene le ADR sulle scelte di build e modularizzazione.

Nota: `docs/module_index.md` elenca tutti i moduli richiesti e documenta anche le cartelle di servizio (es. `quarantine/`, `taverna_saves/`) che non rientrano nel flusso API standard ma vanno tracciate lì; per i dettagli su moduli obbligatori/di servizio vedi la [sezione dedicata](docs/module_index.md#cartelle-di-servizio).

### Requisiti

- Python 3.10+
- `pip install -r requirements.txt`

L'API richiede per default una chiave: esporta `API_KEY` nell'ambiente per abilitarla:

```bash
export API_KEY="la-tua-chiave-segreta"
```

Se vuoi abilitare esplicitamente l'accesso anonimo, imposta `ALLOW_ANONYMOUS=true`. In
assenza di `API_KEY` e senza questo flag, l'API risponderà con `401 Unauthorized` alle
richieste prive di chiave.

### Avvio rapido (user-friendly)

Se stai usando la root del monorepo `pathfinder/`, il comando unico avvia API, frontend e browser:

```bash
python launch.py start
```

Su Windows puoi anche fare doppio click su `start.bat` (o `start.ps1`).

Il launcher:
- crea/usa i venv di `npc-profiler` e `Master-DD-Taverna`;
- rileva automaticamente Ollama su `localhost:11434` e, se presente, imposta `RAG_LLM_PROVIDER=ollama`;
- costruisce l'indice RAG alla prima esecuzione se manca;
- apre il browser su `http://localhost:8501`.

Per eseguire solo i test:

```bash
python launch.py test
```

### Avvio manuale

1. Esporta le variabili d'ambiente: `export API_KEY="la-tua-chiave"` e, se serve accesso senza chiave, `export ALLOW_ANONYMOUS=true`.
2. Installa le dipendenze: `pip install -r requirements.txt`.
3. Esegui il controllo di formattazione e sintassi: `tools/run_static_analysis.sh`.
4. Avvia l'API: `uvicorn src.app:app --reload --port 8000`.
5. Verifica che risponda:

```bash
curl http://localhost:8000/health
curl -H "x-api-key:$API_KEY" http://localhost:8000/modules/minmax_builder
curl http://localhost:8000/modules/minmax_builder        # 401 se la chiave è obbligatoria
curl -H "x-api-key:chiave-sbagliata" http://localhost:8000/modules/minmax_builder  # 429 dopo i tentativi falliti
```

Se incontri errori `401` o `429`, ricordati che il blocco/backoff sullo header `x-api-key` è controllato da `AUTH_BACKOFF_THRESHOLD` e `AUTH_BACKOFF_SECONDS`: aumentali o disattiva la chiave per verificare se gli esiti derivano dalla soglia di tentativi o dal timer di blocco. Consulta il [backoff di autenticazione](#backoff-autenticazione-auth_backoff_) per i dettagli.

> **Audit:** ogni richiesta di build (accettata o bloccata) va tracciata nel blocco `step_audit` del payload e loggata come riga JSON in `data/audit/build_events.jsonl` (esempio in `data/audit/build_events.sample.jsonl`) con timestamp, hash della chiave, IP e stato di backoff.

#### Backoff autenticazione (`AUTH_BACKOFF_*`)

Per mitigare tentativi ripetuti con chiavi errate, puoi regolare il backoff sugli
header `x-api-key` tramite due variabili d'ambiente:

- `AUTH_BACKOFF_THRESHOLD` (default: `5`): numero di richieste fallite prima di attivare
  il blocco temporaneo.
- `AUTH_BACKOFF_SECONDS` (default: `60`): durata del blocco (`429 Too Many Requests` con
  header `Retry-After`) applicato all'IP che ha superato la soglia.

#### Trust proxy headers (`TRUST_PROXY_*`)

Per evitare spoofing degli header, l'API considera `x-forwarded-for` solo se la richiesta
proviene da un proxy esplicitamente fidato:

- `TRUST_PROXY_HEADERS` (default: `false`): se `true`, abilita la lettura degli header proxy.
- `TRUSTED_PROXY_IPS` (default: stringa vuota): lista CSV di IP proxy fidati autorizzati
  a fornire `x-forwarded-for`.

Quando il trust è disabilitato (default), l'identificazione client usa sempre `request.client.host`.
Se il trust è abilitato, il parser accetta solo IP validi IPv4/IPv6 in `x-forwarded-for` e ignora
valori malformati.

Consulta `docs/api_usage.md` per panoramica rapida di endpoint, parametri (`mode`, `stub`, header `x-api-key`) e messaggi d'errore standard.

### Analisi statica

Prima di aprire una PR esegui un controllo veloce di formattazione e sintassi:

```bash
tools/run_static_analysis.sh
```

Lo script lancia `black --check` sui file Python e compila i moduli con
`python -m compileall` per rilevare errori di sintassi.

### Catalogo di riferimento RAW/SRD

- I file normalizzati si trovano in `data/reference/*.json` e seguono lo schema
  `schemas/reference_catalog.schema.json` (chiavi obbligatorie: `name`,
  `source`, `source_id`, `prerequisites`, `tags`, `references`, `reference_urls`;
  campi opzionali: `notes`, `created_at`, `updated_at`, `status`, `validation_status`, `reviewed_by`). Aggiorna i file con nuove voci RAW/SRD citando la
  fonte e mantieni il formato lista di oggetti; `reference_urls` deve includere
  almeno un link AoN e gli ID devono essere univoci.
- Ogni snapshot è versionato in `data/reference/manifest.json` con numero di
  versione, conteggio entry e percorso dei file: quando modifichi il catalogo
  aggiorna il manifest (versione e contatori) e verifica che le fonti restino
  SRD/RAW.
- Il catalogo locale non sostituisce le query runtime verso le fonti
  `meta_community`: è uno snapshot curato offline (per CI/validazioni senza
  rete) che raccoglie gli entry point più ricorrenti. Puoi ampliare l'elenco
  importando i risultati delle ricerche `meta_community` e normalizzandoli
  nello schema condiviso.
- Per validare il catalogo esegui i test: `pytest tests/test_generate_build_db.py -k reference`
  oppure lancia `python -m compileall data/reference schemas` per catturare
  errori di formattazione prima di eseguire lo script di harvest.
- **Gate bloccante build**: esegui `python tools/validate_schemas.py --manifest data/reference/manifest.json --build-dir src/data/builds`; il comando fallisce (exit code `1`) se `reference_catalog_version` non coincide con il manifest o se i dataset `spells/feats/items` non sono coerenti con `entries`.
- L'indice `src/data/module_index.json` espone il catalogo tramite il campo
  `reference_catalog`: aggiungi il manifest se crei nuovi dataset e mantieni
  l'elenco allineato.

#### Siti SRD ammessi e formato delle citazioni

- **Archives of Nethys (aonprd.com)** è la fonte primaria obbligatoria per i
  link SRD: ogni dataset offline deve includere il permalink AoN della voce
  (feat, incantesimo, oggetto). **d20pfsrd.com** va inserito solo come backup,
  mantenendo sempre l’ordine di preferenza AoN → d20pfsrd. Non usare pagine
  riassuntive generiche, PDF non ufficiali o mirror terzi.
- Nei file catalogo valorizza `reference_urls` con URL assoluti SRD e mantieni
  `references` come descrizione leggibile (es. `d20PFSRD: Power Attack`). Quando
  una voce dispone di un URL canonico aggiungilo anche in `references` per
  affiancare alle sigle la citazione pronta all'uso.
- In risposta alle query, il GPT deve citare gli URL SRD con Markdown link o
  testo esplicito, privilegiando i link presenti in `reference_urls` e includendo
  entrambi i siti se disponibili.
- Se esistono più URL validi (es. d20pfsrd e aonprd) puoi elencarli entrambi
  nello stesso campo mantenendo l'ordine di preferenza.

Esempi di uso nelle risposte del GPT:

- **Query**: "Che effetto ha *Fireball*?"
  **Risposta sintetica**: "*Fireball* infligge 1d6 danni da fuoco per livello
  (max 10d6) in un raggio di 6 m, Riflessi dimezza (CD basata sulla tua
  caratteristica da incantatore). Fonte: [d20pfsrd](https://www.d20pfsrd.com/magic/all-spells/f/fireball/) e
  [Archives of Nethys](https://aonprd.com/SpellDisplay.aspx?ItemName=Fireball)".
- **Query**: "Posso usare Rapid Shot con il mio arco composito?"
  **Risposta sintetica**: "Sì, *Rapid Shot* ti dà un attacco extra a penalità
  -2 su tutti gli attacchi a distanza nel round completo. Richiede Des 13 e
  *Point-Blank Shot*. Fonte: [d20pfsrd](https://www.d20pfsrd.com/feats/combat-feats/rapid-shot-combat/)".
- **Query**: "Dove trovo i prerequisiti di *Shatter Defenses*?"
  **Risposta sintetica**: "*Shatter Defenses* richiede Des 13, *Weapon Focus*,
  *Dazzling Display* e BAB +6. Fonte: [Archives of Nethys](https://aonprd.com/FeatDisplay.aspx?ItemName=Shatter%20Defenses)".

#### Query AoN pronte per lo script generativo

Usa questi permalink AoN come base per gli script di raccolta/normalizzazione (aggiungi
solo il parametro `ItemName` o la query desiderata; d20pfsrd resta un backup da
citare solo se AoN è irraggiungibile):

- **Search**: `https://aonprd.com/Search.aspx?Query=<termine+da+cercare>` (esempio: `https://aonprd.com/Search.aspx?Query=power+attack`).
- **FeatDisplay**: `https://aonprd.com/FeatDisplay.aspx?ItemName=<NomeFeat>` (esempio: `https://aonprd.com/FeatDisplay.aspx?ItemName=Shatter%20Defenses`).
- **SpellDisplay**: `https://aonprd.com/SpellDisplay.aspx?ItemName=<NomeIncantesimo>` (esempio: `https://aonprd.com/SpellDisplay.aspx?ItemName=Fireball`).
- **SkillDisplay**: `https://aonprd.com/SkillDisplay.aspx?ItemName=<NomeAbilit%C3%A0>` (esempio: `https://aonprd.com/SkillDisplay.aspx?ItemName=Stealth`).

#### Rigenerare `src/data/module_index.json`

- Aggiorna prima `data/reference/manifest.json` (versione e contatori) se il catalogo RAW/SRD è stato modificato e annota il cambio in `CHANGELOG.md` quando introduci una nuova versione.
- Per riallineare l’indice offline ai moduli scaricati e al manifest corrente, esegui lo snippet seguente dalla root del repository:

  ```bash
  python - <<'PY'
  import json
  from datetime import datetime, timezone
  from pathlib import Path

  modules_dir = Path("src/modules")
  manifest_path = Path("data/reference/manifest.json")
  manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

  entries = []
  for path in sorted(modules_dir.iterdir(), key=lambda p: p.name.lower()):
      if not path.is_file():
          continue
      stat = path.stat()
      entries.append(
          {
              "module": path.name,
              "file": str(path),
              "status": "ok",
              "meta": {
                  "name": path.name,
                  "suffix": path.suffix,
                  "size_bytes": stat.st_size,
              },
          }
      )

  module_plan = [entry["module"] for entry in entries]
  files_info = manifest.get("files", {}) if isinstance(manifest, dict) else {}
  catalog_version = manifest.get("version") if isinstance(manifest, dict) else None

  reference_catalog = [
      {
          "path": str(files_info.get(key, {}).get("path", f"data/reference/{key}.json")),
          "entries": files_info.get(key, {}).get("entries"),
          "version": catalog_version,
      }
      for key in ("spells", "feats", "items")
  ]
  reference_catalog.append({"path": str(manifest_path), "version": catalog_version})

  payload = {
      "generated_at": datetime.now(timezone.utc)
      .replace(microsecond=0)
      .isoformat()
      .replace("+00:00", "Z"),
      "api_url": None,
      "catalog_version": [catalog_version] if catalog_version else [],
      "entries": entries,
      "module_plan": module_plan,
      "reference_catalog": reference_catalog,
  }

  Path("src/data/module_index.json").write_text(
      json.dumps(payload, indent=2) + "\n", encoding="utf-8"
  )
  PY
  ```
- Il comando aggiorna `generated_at`, sincronizza `reference_catalog` con i file versionati e mantiene il piano dei moduli coerente con le risorse presenti in `src/modules`. `src/data/modules/` resta la directory di output per i dump scaricati da `generate_build_db.py`.

### Flag CLI per validazione catalogo e combo T1

`tools/generate_build_db.py` ora integra la verifica contro il catalogo
`data/reference/` e la generazione opzionale di combo T1:

- `--reference-dir data/reference` punta alla directory del catalogo e del
  manifest versionato (iniettato nei metadati delle build).
- `--validate-combo` richiede che ogni scheda e ledger siano coerenti con il
  catalogo (incantesimi, talenti, equipaggiamento) e aggiunge errori di
  completezza se mancano voci/prerequisiti o se il ledger contiene elementi non
  presenti nella scheda.
- `--suggest-combos` genera varianti combinando archetipi/talenti/equipaggiamento
  dal catalogo, esegue il builder e salva nelle metadati solo le proposte con
  `benchmark.meta_tier == "T1"` e `ruling_badge` valido. Con `--validate-combo`
  i log dei ruling e l'assenza di combo T1 vengono riportati in
  `completeness.errors`. I suggerimenti ora sfruttano tag granulari (es.
  `class:magus`, `archetype:swashbuckler`, `slot:headband`, `damage:fire`,
  `school:evocation`) per scegliere oggetti e talenti compatibili con la
  classe/archetipo richiesto. Esempi:

  ```bash
  python tools/generate_build_db.py --class Ranger \
    --suggest-combos --validate-combo --reference-dir data/reference \
    --api-url http://localhost:8000

  python tools/generate_build_db.py --class Magus --archetype "eldritch scion" \
    --suggest-combos --reference-dir data/reference --mode extended
  ```

L'output arricchito include:

- `completeness.errors` popolato con assenze/prerequisiti, disallineamenti
  sheet/ledger e, se richiesto, l'assenza di combo T1 valide.
- `benchmark.suggested_combos` con le varianti accettate e i relativi log di
  ruling/benchmark, oltre al versionamento del catalogo utilizzato.

Su push e pull request, il workflow GitHub Actions **Static Analysis** esegue
lo stesso script per garantire che il codice resti formattato e privo di errori
di sintassi prima del merge.

### Policy PR e controlli CI

Ogni pull request deve includere report normalizzati in `reports/module_tests/`
e passare entrambi i job CI:

- **report-check**: valida i report con `python tools/refresh_module_reports.py --check` (exit code 1 blocca il merge).
- **static-analysis**: esegue `./tools/run_static_analysis.sh` per verificare formattazione e compilazione dei moduli.

Per verificare in locale:

```bash
python tools/refresh_module_reports.py --check
./tools/run_static_analysis.sh
```

### Aggiornare le sezioni dei report dei moduli

Per allineare i report QA in `reports/module_tests/` alla checklist standard
(Ambiente, Esiti API, Metadati, Comandi/Flow, QA, Osservazioni, Errori,
Miglioramenti suggeriti, Fix necessari) puoi usare lo script
`tools/refresh_module_reports.py`, che legge automaticamente la sequenza moduli
da `planning/module_review_guide.md` e applica i placeholder `- TODO` nelle
sezioni obbligatorie (creando i report mancanti quando serve):

```bash
# Verifica che ogni report contenga tutte le sezioni richieste con almeno un bullet
python tools/refresh_module_reports.py --check

# Aggiunge le sezioni mancanti con bullet placeholder "- TODO"
python tools/refresh_module_reports.py --write
```

Usa `--check` nei workflow CI per bloccare report con heading mancanti o senza
contenuto; `--write` aggiorna in loco i file mancanti senza toccare il
contenuto esistente. Se il file sorgente di un modulo non è presente in
`src/modules/`, lo script mostra un warning ma prosegue la normalizzazione del
report.

Nota operativa: prima di avviare una revisione manuale dei report esegui `python tools/refresh_module_reports.py --write` per
allineare i file locali; nelle pipeline CI aggiungi un passaggio dedicato (o un target equivalente) che lanci `python
tools/refresh_module_reports.py --check` per impedire il merge di report senza tutte le sezioni.
Quando generi il piano operativo (`python tools/generate_module_plan.py --output planning/module_work_plan.md`) esegui prima
`python tools/refresh_module_reports.py --write` (o `--check` nei workflow) così il piano si basa su report già normalizzati e
con tutte le intestazioni/template applicati.

### Workflow QA quotidiano

Usa questo mini-flusso per mantenere allineati report e piano di lavoro lungo la giornata. Il comando
`bash tools/daily_workflow.sh` orchestra in sequenza i passaggi già elencati (normalizzazione dei
report, generazione del piano, analisi statica) producendo/validando i file
`reports/module_tests/*.md` e `planning/module_work_plan.md` (più l'eventuale executive plan). Per
una corsa solo di validazione lancia `bash tools/daily_workflow.sh --check-only`, che mantiene i
report immutati e si limita a verificare che il piano sia generabile. Se ti servono percorsi
alternativi per i piani, passa `--plan-path` e/o `--exec-plan-path` (es. per salvare una copia
temporanea durante gli esperimenti).

- **Mattina**
  - Normalizza i report in [`reports/module_tests/`](reports/module_tests/) con le sezioni obbligatorie: `python tools/refresh_module_reports.py --write`. Se lo script stampa
    `Aggiornato: reports/module_tests/<modulo>.md` e termina con exit code `0`, sei pronto a compilare; se ricevi messaggi
    `[WARN]` o l'uscita è `1`, rilancia con `--write` finché non scompaiono le segnalazioni di sezioni mancanti.
  - Genera il piano operativo completo: `python tools/generate_module_plan.py --output planning/module_work_plan.md`. L'output
    atteso chiude con `Work plan written to planning/module_work_plan.md` (exit code `0`); in caso di errore interrompi la
    sessione e controlla che i report siano stati aggiornati prima di rilanciare.
  - Annota i task emersi o le dipendenze in `planning/roadmap.md` (es. nuove verifiche, blocker tecnici) per tenerli tracciati.

- **Durante la lettura**
  - Compila le sezioni dei report applicando le lenti PF1e (coerenza con regole, scaling e build) e sicurezza/observability
    (risposte API, backoff, metriche, logging) quando aggiorni `QA`, `Osservazioni`, `Errori` e `Miglioramenti` in
    [`reports/module_tests/`](reports/module_tests/).
  - Mantieni almeno un bullet per sezione; se lo script precedente ha inserito `- TODO`, sostituiscilo con l'esito reale prima
    di procedere oltre.

- **Fine giornata**
  - Verifica che i report compilati siano completi: `python tools/refresh_module_reports.py --check`. L'uscita attesa è
    `Tutti i report includono le sezioni obbligatorie con almeno un bullet.` e exit code `0`; se esce `1` con elenco delle
    sezioni mancanti/ vuote, riapri i file indicati e sistemali prima di ripetere il comando.
  - Rigenera (se necessario) il piano di lavoro con `python tools/generate_module_plan.py --output planning/module_work_plan.md`
    per riflettere gli ultimi aggiornamenti e sincronizza i task residui in `planning/roadmap.md`.

Per i moduli, il dump completo è **disattivato di default** (`ALLOW_MODULE_DUMP=false`).
`/modules/{name}` restituisce solo estratti (4000 caratteri + marcatore finale) e blocca
gli asset non testuali: la risposta include `X-Content-Partial: true` e `206 Partial Content`
per segnalare che il contenuto è incompleto. Imposta `ALLOW_MODULE_DUMP=true` solo se
ti serve il dump completo per QA o export.

Per monitorare i salvataggi generati dal flusso Taverna, sono disponibili gli endpoint
`GET /modules/taverna_saves/meta` (path, quota `max_files`, spazio residuo, policy di
overflow) e `GET /modules/taverna_saves/quota` (occupazione rapida della cartella). Il
payload include note di remediation per Echo gate <8.5 (ripeti /grade, usa /refine_npc o,
in sandbox, disattiva temporaneamente con /echo off) e per QA CHECK bloccanti: completa
Canvas+Ledger, ripeti /self_check e verifica Echo ≥ soglia prima di rilanciare /save_npc o
/npc_export (bloccati finché QA=CHECK o Echo è sotto soglia).

`POST /pc/build` — costruzione deterministica PG livelli 1-20 dai cataloghi OGL (point-buy, razza, classe, skill, talenti, tratti, equip; 422 con lista errori di validazione. Per lv>1 l'equipment è best-effort con warning anziché errori: ricchezza da Wealth by Level (WBL, vedi `src/pc/catalogs.py`), item non in catalogo (es. oggetti magici) e spesa oltre il WBL segnalati come warning. Gli effetti meccanici dei talenti supportati (passivi scalati col livello, Weapon/Skill Focus, Weapon Finesse — vedi `src/pc/feat_effects.py`) vengono applicati ai valori; gli altri sono solo validati). Vedi `src/pc/`.

### Avvio API locale

User-friendly (dalla root del monorepo):

```bash
python launch.py start-master
```

Manuale (da dentro questa cartella):

```bash
export API_KEY="la-tua-chiave"
# opzionale: sblocca l'accesso senza chiave
# export ALLOW_ANONYMOUS=true
uvicorn src.app:app --reload --port 8000
```

L'endpoint di base sarà ad esempio: `http://localhost:8000`

Prima di lanciare `--discover-modules`, assicurati che l'API sia effettivamente raggiungibile: avvia `uvicorn src.app:app --reload --port 8000` oppure imposta `--api-url` verso un host già in esecuzione. Se l'API reale non è disponibile, puoi utilizzare lo stub locale `tools/mock_builder_server.py` per simulare le risposte necessarie.

Variabili chiave (anche per run schedulati):

- `API_KEY`: obbligatoria per tutti gli endpoint protetti; se non valorizzata, abilita eventualmente `ALLOW_ANONYMOUS=true` per test locali/stub.
- `ALLOW_ANONYMOUS`: consente di saltare il controllo della chiave sugli endpoint principali, utile solo in ambienti controllati.
- `METRICS_API_KEY` e `METRICS_IP_ALLOWLIST`: la prima abilita `/metrics` anche con la chiave generale, la seconda consente l'accesso tramite IP trusted.
- `AUTH_BACKOFF_THRESHOLD`/`AUTH_BACKOFF_SECONDS`: soglia e finestra del blocco che restituisce `429` e header `Retry-After` quando la chiave non è valida; alza i valori se i run schedulati accumulano tentativi ravvicinati.
- `API_URL`, `HEALTH_PATH`, `HEALTH_TIMEOUT`: endpoint base e probe usati da `generate_build_db.py` quando gira in cron/CI; `HEALTH_PATH` copre anche host che espongono health su percorsi diversi, `HEALTH_TIMEOUT` gestisce latenze elevate.

Durante il setup nel GPT, forza sempre la modalità esplicita (`/set_mode core` oppure `/set_mode extended`) e verifica che l'avanzamento riporti `[step/step_total]` coerente: 8 step per `core`, 16 per `extended`.

## Usare con LLM open source / locali (RAG)

Il bundle GPT è stato esteso con un layer **RAG (Retrieval-Augmented Generation)**
che permette di interrogare moduli e catalogo reference con LLM locali (Ollama)
o API compatibili OpenAI, senza dipendere da ChatGPT.

Cosa è incluso:

- Vector store persistente in `src/data/vector_store/` (numpy + JSON).
- Script di indicizzazione: `tools/index_rag.py`.
- Endpoint FastAPI: `POST /rag/search`, `POST /rag/ask`, `POST /rag/build`.
- Provider LLM: `mock` (offline), `ollama` (endpoint nativo), `ollama-openai` (endpoint OpenAI-compatible locale), `openai` (API compatibile OpenAI/cloud).
- Frontend web di chat: `frontend/rag_chat.py` (Streamlit).
- Build agent per generare schede PF1E via RAG: `src/agents/builder.py` + CLI `tools/build_agent.py`.

Per installare, indicizzare e usare il RAG vedi la guida dedicata:

**[`OPEN_SOURCE_RAG.md`](OPEN_SOURCE_RAG.md)**

Comandi rapidi (dalla root del monorepo `pathfinder/`):

```bash
# 1. Setup venv e dipendenze
python launch.py setup

# 2. Avvia API + frontend + browser (auto-detect Ollama)
python launch.py start

# 3. Prova una domanda in modalità mock (nessun LLM esterno)
curl -X POST http://localhost:8000/rag/ask \
  -H "Content-Type: application/json" \
  -H "x-api-key: test" \
  -d '{"query": "cosa fa Power Attack?", "top_k": 5, "provider": "mock"}'
```

Comandi manuali avanzati (da dentro questa cartella):

```bash
# 1. Indicizza
.venv/Scripts/python tools/index_rag.py

# 2. Avvia API
.venv/Scripts/uvicorn src.app:app --reload --port 8000

# 3. Prova una domanda in modalità mock (nessun LLM esterno)
curl -X POST http://localhost:8000/rag/ask \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"query": "cosa fa Power Attack?", "top_k": 5, "provider": "mock"}'

# Oppure chat web
.venv/Scripts/streamlit run frontend/rag_chat.py

# Oppure genera una build
.venv/Scripts/python tools/build_agent.py --class Fighter --race Human --level 5 --focus DPR --provider mock
```

Stato test: `114 passed, 1 skipped` (inclusi `tests/test_rag.py` e `tests/test_build_agent.py`).

### Generare il database di build (e i dump dei moduli)

Uno script di utilità (`tools/generate_build_db.py`) raccoglie automaticamente le build PF1e per tutte le classi target interrogando l'endpoint del **MinMax Builder** e, in parallelo, scarica i moduli grezzi indispensabili per ricostruire schede complete (base profile, taverna/narrativa, template scheda):

```bash
# Assicurati di avere l'API in esecuzione e una chiave valida
# Nota: valida sempre /health e /metrics con l'API key corretta prima dei run;
# usa curl con retry parametrizzabili per assorbire spike transitori (timeout/429):
#
#   HEALTH_RETRIES=${HEALTH_RETRIES:-5}
#   HEALTH_RETRY_DELAY=${HEALTH_RETRY_DELAY:-2}
#   METRICS_RETRIES=${METRICS_RETRIES:-5}
#   METRICS_RETRY_DELAY=${METRICS_RETRY_DELAY:-2}
#   curl --retry "$HEALTH_RETRIES" --retry-delay "$HEALTH_RETRY_DELAY" --retry-all-errors \
#     -H "x-api-key: ${API_KEY}" "${API_URL:-http://localhost:8000}${HEALTH_PATH:-/health}"
#   curl --retry "$METRICS_RETRIES" --retry-delay "$METRICS_RETRY_DELAY" --retry-all-errors \
#     -H "x-api-key: ${METRICS_API_KEY:-$API_KEY}" "${API_URL:-http://localhost:8000}${METRICS_PATH:-/metrics}"
# Se ricevi 401/429 regola AUTH_BACKOFF_THRESHOLD/SECONDS per aumentare il margine.
# Se l'API non gira in locale, passa un endpoint raggiungibile oppure usa
# la variabile API_URL per evitare errori di connessione su http://localhost:8000
export API_KEY="la-tua-chiave-segreta"
# Esempio con endpoint locale
python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended
# Esempio con endpoint remoto/containerizzato
# API_URL="https://builder.example.com" python tools/generate_build_db.py --mode extended
# Se l'endpoint non espone /health ma sai che è raggiungibile, aggiungi --skip-health-check
# Se il probe richiede un path/timeout personalizzati puoi usare --health-path e --health-timeout
# Nota: quando non usi `--skip-ruling-expert` devi passare esplicitamente l'endpoint del ruling expert con
# `--ruling-expert-url <endpoint>/modules/ruling-expert`, altrimenti la fase di ruling non parte. Esempio completo:
python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --ruling-expert-url http://localhost:8000/modules/ruling-expert
# Solo per debug/local stub puoi saltare il ruling expert con
python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --skip-ruling-expert

# È possibile limitare le classi passandole come argomenti finali
python tools/generate_build_db.py Alchemist Wizard Paladin

# Oppure filtrare a monte le richieste provenienti dalla spec con le flag dedicate
# (utile per rigenerare blocchi di 5 classi per volta)
python tools/generate_build_db.py --spec-file docs/examples/pg_variants.yml --classes Alchemist Barbarian Bard Cavalier Cleric

# Puoi anche limitare i checkpoint di livello a un sottoinsieme preciso
python tools/generate_build_db.py --spec-file docs/examples/pg_variants.yml --levels 1 5

# Se devi generare batch piccoli (es. 10 file alla volta) puoi impostare un tetto
python tools/generate_build_db.py --max-items 10 --skip-unchanged

# Quando hai bisogno di riavviare batch successivi, combina max-items con offset/paginazione
python tools/generate_build_db.py --max-items 10 --offset 0   # Batch 1
python tools/generate_build_db.py --max-items 10 --offset 10  # Batch 2
python tools/generate_build_db.py --max-items 10 --offset 20  # Batch 3 (e così via)
python tools/generate_build_db.py --max-items 10 --page 1 --page-size 10  # Equivalente a offset 0
python tools/generate_build_db.py --max-items 10 --page 2 --page-size 10  # Equivalente a offset 10
# Ripeti incrementando l'offset/la pagina finché non hai coperto tutte le classi e i checkpoint richiesti
```

Lo script si appoggia ai valori di ambiente `API_URL`, `API_KEY` e, se necessario, `HEALTH_PATH`/`HEALTH_TIMEOUT` per i probe iniziali (o `--health-*` da CLI). In caso di `401` o `429` con header `Retry-After` vengono registrati eventi in `data/audit/build_events.jsonl` per tracciare backoff e ritentativi dell'orchestratore schedulato.

Per impostazione predefinita usa la modalità `extended` (16 step completi) e salva l'output in `src/data/builds/<classe>.json`, creando anche un indice riassuntivo in `src/data/build_index.json` con lo stato di ogni richiesta. In parallelo scarica i moduli RAW più usati dal flusso (per schede e PG completi) in `src/data/modules/` con indice `src/data/module_index.json`. L'header `x-api-key` viene popolato dalla variabile d'ambiente `API_KEY` salvo override esplicito tramite `--api-key`. Ogni chiamata include il parametro `mode=core|extended` e l'indice registra lo `step_total` osservato, così puoi verificare che i 16 step appaiano solo quando richiedi `extended`.

Ogni build viene recuperata sui checkpoint di livello dichiarati nella spec (default 1/5/10) e scritta in file separati con suffisso `_lvlXX` (es. `Fighter_lvl05.json`): le entry dell'indice `build_index.json` includono il campo `level` e un riepilogo `checkpoints` con i totali/invalidi (incluse le invalidazioni di schema o completezza) per ciascun livello.

#### Troubleshooting

- Endpoint senza `/health`: aggiungi `--skip-health-check` per saltare il probe iniziale quando l'API è accessibile ma non espone l'handler di health (o usa l'ambiente `API_URL` per puntare a un host remoto se non è `localhost`).
- Validazione schema fallita: usa `--strict` per far fallire lo script al primo JSON non conforme; con `--keep-invalid` salvi comunque le risposte difettose per ispezionarle. In `build_index.json` troverai gli esiti dei singoli step (`status`, `errors`, `step_total`) e puoi capire quale build/race/archetipo ha rotto lo schema; `module_index.json` riporta eventuali moduli scartati o corrotti con `validation_errors`.
- Copertura vs resilienza: con `--dual-pass` lo script esegue prima un round fail-fast (`--strict`) e poi uno tollerante che forza `--keep-invalid`, così puoi confrontare copertura e errori. Aggiungi `--dual-pass-report reports/dual_pass.json` per salvare un riepilogo e `--invalid-archive-dir artifacts/invalid_payloads` per copiare automaticamente i payload non conformi segnalati dagli indici.
- Host remoto non raggiungibile su `localhost`: esporta `API_URL` o passa `--api-url https://builder.example.com` per indirizzare lo script verso l'endpoint corretto, anche dietro tunnel/port-forward.

Esempi rapidi:

```bash
# Forza la validazione rigorosa e interrompe al primo errore
python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --strict

# Mantiene i payload non validi per analisi successive
python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --keep-invalid
```

Per verificare rapidamente la copertura dei checkpoint (1/5/10) delle build già presenti nel repository senza contattare l'API, puoi esportare tre report JSON sotto `reports/` con la flag `--export-lists`:

```bash
python tools/generate_build_db.py --export-lists
# opzionale: cambia cartella di destinazione dei report
python tools/generate_build_db.py --export-lists --reports-dir reports/build_coverage
```

I file generati (`build_classes.json`, `build_races.json`, `checkpoint_coverage.json`) riepilogano le classi, le razze e i prefissi di filename con i checkpoint disponibili, quelli mancanti e il totale di file per livello.

Per mantenere sincronizzato l'inventario delle razze con i JSON presenti in `src/data/builds` puoi anche esportare solo il report delle razze:

```bash
python tools/generate_build_db.py --export-races
```

Il file `reports/build_races.json` include ora un campo `unused_preferred_races` che elenca le razze del pool PF1e predefinito (`--race-pool`) ancora non usate: con l'inventario attuale sono `Elf`, `Gnome`, `Half-Elf`, `Human`, `Dhampir`, `Drow`, `Hobgoblin`, `Ifrit`, `Kobold`, `Orc`, `Oread`, `Ratfolk`, `Undine`, `Changeling`, `Gillman`, `Merfolk`, `Nagaji`, `Svirfneblin`, `Wyvaran`, `Advanced Android`, `Android`, `Aphorite`, `Automaton`, `Centaur`, `Duergar`, `Gathlain`, `Lashunta`, `Minotaur`, `Oni-Spawn`, `Samsaran (Reborn)`, `Skinwalker`, `Trox`, `Wyrwood`. Puoi passarle direttamente a `--race-pool` insieme a `--prefer-unused-race` per assegnare automaticamente la prima razza libera alle richieste senza razza esplicita:

```bash
PREFERRED_UNUSED_RACES=$(jq -r '.unused_preferred_races[]' reports/build_races.json | xargs)
python tools/generate_build_db.py --ruling-expert-url http://localhost:8000/modules/ruling-expert --prefer-unused-race --race-pool $PREFERRED_UNUSED_RACES
```


#### Selezione moduli: statici o via discovery

- Con `--modules` puoi continuare a pinnare manualmente i file da scaricare (default: i 5 moduli critici per scheda/narrativa).
- Con `--discover-modules` lo script interroga `GET /modules` e unisce i risultati ai moduli espliciti, così non perdi nuovi asset pubblicati sull'API.
- Puoi applicare filtri glob solo ai moduli scoperti: `--include '*.txt' modules/*` limita i download ai pattern indicati, mentre `--exclude 'beta_*'` rimuove i match specificati. L'indice `module_index.json` annota timestamp e filtri usati nella discovery per riprodurre esattamente la lista.

Esempi:

```bash
# Scarica i moduli statici + tutto ciò che è visibile via /modules
python tools/generate_build_db.py --discover-modules

# Scarica solo i moduli .txt scoperti e mantiene un modulo extra pinnato
python tools/generate_build_db.py --discover-modules --include '*.txt' --modules base_profile.txt meta_doc.txt

# Escludi gli asset di test ma lascia i moduli espliciti
python tools/generate_build_db.py --discover-modules --exclude 'test_*' --modules base_profile.txt scheda_pg_markdown_template.md
```

I file generati sono consumabili come database locale per esport, benchmark e stato di build: ogni JSON contiene i campi `build_state`, `benchmark` ed `export` prodotti dal builder, più metadati di fetch (`class`, `mode`, `source_url`). I moduli scaricati (es. `base_profile.txt`, `Taverna_NPC.txt`, `narrative_flow.txt`, `scheda_pg_markdown_template.md`, `adventurer_ledger.txt`) rimangono grezzi e coerenti con l'API così da poter combinare build, scheda e narrativa mantenendo varianti di classe/razza/archetipo definite dai moduli stessi.

Per orchestrare richieste più articolate (classe + razza/archetipo/modello + hook di background) puoi usare `--spec-file` con un file YAML/JSON che descrive ogni PG. Ogni voce definisce la classe, eventuali parametri addizionali da passare come query/body e il prefisso del file di output. Se non passi `--spec-file` viene caricato automaticamente `docs/examples/pg_variants.yml`, così da coprire almeno un set di combinazioni razza/archetipo per le classi chiave. In alternativa puoi far generare un prodotto cartesiano di varianti con le nuove flag CLI: `--races`, `--archetypes`, `--background-hooks` (tutti opzionali), abbinate alla lista di classi finale.

Il JSON di risposta includerà anche le sezioni extra restituite dall'API (es. narrativa, markup scheda, ledger) in `composite.{narrative|sheet|ledger}`, mentre l'indice `build_index.json` annoterà le varianti (`class`, `race`, `archetype`, `mode`, `spec_id`, `background`) per misurare copertura e refill del DB.

Esempio di spec (`docs/examples/pg_spec.yml`):

```yaml
# Mode di default per le richieste senza override
mode: extended
requests:
  - id: mm-hellknight-elf
    class: Fighter
    race: Elf
    archetype: Hellknight Armiger
    model: "Armiger (Hellknight)"
    background_hooks: "Giurata dell'Ordine del Pyre, addestrata alla disciplina inflessibile."
    output_prefix: fighter_hellknight_elf
    query:
      race: Elf
      archetype: Hellknight Armiger
      theme: "hellknight armiger"
      homebrewery_ready: true
    body:
      hooks:
        - "Servire l'Ordine e affrontare minacce extraplanari"
        - "Cerca una via di redenzione per un peccato passato"
      sheet_locale: it-IT
```

Invocazione con spec (genera build + narrativa + markup scheda + ledger se restituiti dal builder):

```bash
python tools/generate_build_db.py --api-url http://localhost:8000 --spec-file docs/examples/pg_spec.yml --modules base_profile.txt narrative_flow.txt scheda_pg_markdown_template.md adventurer_ledger.txt
```

Ogni payload recuperato viene validato rispetto agli schemi JSON disponibili in `schemas/`:

- `build_core.schema.json` verifica le risposte minime (solo `build_state`, `benchmark`, `export`).
- `build_extended.schema.json` richiede almeno una sezione addizionale (narrativa, scheda o ledger).
- `build_full_pg.schema.json` si aspetta il blocco composito completo con sezioni aggiuntive del PG.
- `module_metadata.schema.json` valida i metadati restituiti da `/modules/{name}/meta` prima di salvare i file.

Il comportamento di validazione è configurabile:

- Di default l'esecuzione è *warn-only*: gli errori di schema vengono loggati e annotati negli indici (`build_index.json`, `module_index.json`) ma l'esecuzione prosegue.
- Usa `--strict` per interrompere subito alla prima anomalia di validazione.
- Con `--keep-invalid` puoi chiedere allo script di scrivere comunque i file che non superano la validazione; in assenza del flag gli output non validi vengono scartati.

Per la scheda Markdown (`scheda_pg_markdown_template.md`) il payload viene validato contro `schemas/scheda_pg.schema.json`, che copre:

- Flag di rendering opzionali (`print_mode`, `show_minmax`, `show_vtt`, `show_qa`, `show_explain`, `show_ledger`, `decimal_comma`).
- Blocchi numerici e riepiloghi (`statistiche`, `statistiche_chiave`, `salvezze`, bonus CA/attacco/danni, slot incantesimi, CD scuola). Questi campi accettano anche numeri in formato stringa per compatibilità con l'API.
- Metadati di build e benchmark (`classi`, `benchmarks`, `benchmark_comparison`, etichetta `benchmark_reference_label`).
- Sezioni testuali di supporto (`rules_status_text`, `ap_warning`, `uncertainty_flags`, `glossario_golarion`, `fonti`, `fonti_meta`, `spoiler_mode`).
- Ledger opzionale (`ledger_invested_gp`, `ledger_encumbrance_hint`, movimenti/parcel/crafting PFS, valute `currency`).

Esempio di payload valido per la scheda (estratto da una risposta del builder, con campi opzionali popolati):

```json
{
  "class": "Fighter",
  "export": {
    "sheet_payload": {
      "print_mode": false,
      "show_minmax": true,
      "show_vtt": true,
      "decimal_comma": true,
      "classi": [{"nome": "Fighter", "livelli": 7, "archetipi": ["Lore Warden"]}],
      "statistiche": {"FOR": 18, "DES": 16, "COS": 14, "INT": 14, "SAG": 10, "CAR": 8},
      "statistiche_chiave": {"PF": 67, "CA": 24, "DPR_Base": 21.5, "meta_tier": "T3"},
      "salvezze": {"Tempra": 9, "Riflessi": 7, "Volontà": 3},
      "benchmarks": {"meta_tier": "T3", "DPR_late_status": "ok", "risk_top3": {"feats": [], "spells": []}},
      "attack_bonus": {"melee": "+13/+8", "ranged": "+11/+6"},
      "damage": {"melee": "2d6+9", "special": "Power Attack attivo"},
      "fonti": ["CRB", "APG"],
      "fonti_meta": [{"badge": "PFS", "tipo": "boon", "link": "https://example.test/boon"}],
      "rules_status_text": "PFS-legal con boons annotati",
      "ledger_invested_gp": 5300,
      "ledger_movimenti": [
        {"data": "4712-08-01", "tipo": "acquisto", "oggetto": "Full Plate", "qty": 1, "tot": 1500, "pfs": true}
      ],
      "ledger_parcels": [{"nome": "Diamante", "val_gp": 500, "assegnatario": "party"}],
      "currency": {"gp": 245, "sp": 12}
    }
  }
}
```

Con la modalità *warn-only* i fallimenti di validazione della scheda o del payload build non interrompono il download: l'entry corrispondente negli indici viene marcata `status: "invalid"` con un campo `error` descrittivo, ma il resto delle richieste continua. In `--strict` l'errore viene propagato e l'esecuzione termina alla prima violazione; con `--keep-invalid` il file JSON o il modulo raw vengono comunque salvati accanto all'indice, utile per ispezionare manualmente i dati difettosi.

Se hai già generato il database e vuoi avviare una review offline, usa la nuova modalità di sola validazione: non effettua chiamate di rete e produce un report riassuntivo (per default `src/data/build_review.json`).

```bash
python tools/generate_build_db.py --validate-db --review-output src/data/build_review.json
```

Il report include conteggi di build e moduli validi/invalidi, file mancanti e relativi errori di schema così da facilitare la revisione manuale. Nella sezione `builds.checkpoints` trovi il riepilogo dei checkpoint di livello (per default 1/5/10) con totali, invalidazioni e conteggi distinti per errori di schema o completezza, così puoi identificare rapidamente quali livelli sono più fragili. Lo stesso riepilogo viene scritto anche in `build_index.json`, affiancato alle entry per livello generate con suffisso `_lvlXX`.

Il report ora include anche la sezione `reference_urls` con una metrica di copertura AoN vs d20pfsrd sui reference locali (spells/feats/items). Se `status` è `invalid` significa che esistono entry `reference_urls` solo d20pfsrd per elementi ufficiali che hanno un equivalente AoN noto: `missing_aon_entries` elenca i record (es. `feats:Alertness`) da correggere. Per risolvere, apri il file corrispondente in `data/reference/*.json`, aggiungi l'URL AoN (`https://aonprd.com/...`) alla lista `reference_urls` e rigenera la review: il conteggio `aon` deve crescere mentre `d20_only` torna a 0.

### Endpoints principali

- `GET /health` — ping rapido
- `GET /modules` — lista dei file modulo disponibili
- `GET /modules/{name}` — contenuto testuale di un modulo (es. `base_profile.txt`)
- `GET /modules/{name}/meta` — info sintetiche sul modulo (dimensione, tipo) + versioning/compatibilità se presenti nell'header
- `GET /knowledge` — lista risorse PDF/MD disponibili
- `GET /knowledge/{name}/meta` — metadata su una risorsa

Per tutti gli endpoint di moduli e knowledge è richiesto l'header `x-api-key` che deve
contenere il valore configurato in `API_KEY`. L'accesso anonimo è disabilitato di default;
per aprirlo è necessario impostare `ALLOW_ANONYMOUS=true`.

> Nel builder GPT userai il file `gpt/openapi.json` come **Actions Spec** e il testo
> di `gpt/system_prompt_core.md` come **istruzioni**. Così il GPT non deve più contenere
> l'intero `base_profile.txt`, ma può chiedere all'API i moduli quando servono.

## Asset di knowledge pack inclusi

Sono già presenti quattro PDF in `src/data` utilizzati dai moduli/knowledge pack:

- `Homebrewery Formatting Guide (V3) - The Homebrewery.pdf`
- `Items Master List.pdf`
- `The Gear Guide.pdf`
- `Ultimate Crafter Guide.pdf`

## Asset opzionali (non inclusi)

Le azioni per importare pregens PFS o generare Record Sheet CUP non sono abilitate perché
richiedono pacchetti zip non distribuiti. Se vuoi attivarle:

1. Scarica i pacchetti ufficiali e rinominali come `pfs_pregens.zip` e `record_sheets.zip`.
2. Copiali in `src/data/`.
3. Aggiorna `src/modules/Taverna_NPC.txt` per puntare ai nuovi asset (sezione `assets`) e
   riabilitare i flag/azioni corrispondenti.
