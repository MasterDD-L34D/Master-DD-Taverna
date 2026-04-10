# Piano di esecuzione post-kickoff

Questo documento coordina l'esecuzione dei lavori dopo il kickoff: l'obiettivo è chiudere le osservazioni/errori tracciati in `planning/module_work_plan.md`, garantire che le dipendenze siano verificate e che i moduli restino allineati alle policy di export/dump.

## Obiettivo
Concludere il ciclo di remediation per tutti i moduli contrassegnati "Pronto per sviluppo", trasformando le osservazioni/errori in fix verificati e rilasciati, senza introdurre regressioni nelle policy di sicurezza (dump/troncamento, autenticazione, naming export) né nei gate QA condivisi.

## Baseline
- Tutti i moduli sono marcati "Pronto per sviluppo" con priorità massima P1 già coperta; le principali osservazioni ancora da chiudere riguardano `sigilli_runner_module` (7), `Encounter_Designer` (3), `base_profile` (3) e altri moduli minori.【F:planning/module_work_plan.md†L243-L270】
- `base_profile` richiede preload e binding ai moduli core come unica dipendenza del router, da verificare prima dei rilasci dipendenti.【F:planning/module_work_plan.md†L105-L109】
- Le note di dump/troncamento e naming export sono già allineate nei moduli chiave (Encounter_Designer, minmax_builder, Taverna_NPC) e vanno mantenute durante i fix.【F:planning/module_work_plan.md†L12-L19】【F:planning/module_work_plan.md†L25-L35】【F:planning/module_work_plan.md†L66-L74】


## Baseline corrente
Fonte baseline obbligatoria: `reports/build_review.json`, `reports/index_analysis.json`, `reports/data_quality_report.json`, `reports/checkpoint_coverage.json`.

### KPI minimi (fotografia baseline)
- **Copertura classi core (`index_analysis.json`):** 4/10 classi core presenti nelle build indicizzate (`Cleric`, `Druid`, `Paladin`, `Wizard`) e 6/10 mancanti (`Barbarian`, `Bard`, `Monk`, `Ranger`, `Rogue`, `Sorcerer`).
- **Mismatch indice/filesystem (`data_quality_report.json` + `checkpoint_coverage.json`):** 64 gap su `build_index` (49 `level_missing`, 15 `missing_levels`) e 21 prefissi con checkpoint incompleti (attesi 1/5/10).
- **Errori schema/stato build (`build_review.json` + `index_analysis.json`):** 0 build valide su 105 totali (`invalid=76`, `missing=29`); tutte le 76 voci presenti in `build_index` risultano `invalid`.

### Soglia di accettazione minima per avanzamento
- Nessuna release candidate può essere proposta se uno dei KPI sopra peggiora rispetto alla baseline corrente.
- Ogni aggiornamento KPI deve citare esplicitamente il timestamp `generated_at` dei 4 report baseline.

## Cadenza refresh report (operativa)
Per mantenere i report in `reports/` allineati con la baseline, eseguire la seguente routine:

1. **Refresh modulo/QA (giornaliero, o a ogni merge su main):**
   - `python tools/refresh_module_reports.py`
2. **Refresh indici/build list (giornaliero dopo refresh moduli, obbligatorio prima di ogni release candidate):**
   - `python tools/generate_build_db.py --export-lists --output-dir src/data/builds --modules-output-dir src/data/modules --index-path src/data/build_index.json --module-index-path src/data/module_index.json`
3. **Output target da aggiornare in `reports/`:**
   - `reports/build_review.json`
   - `reports/index_analysis.json`
   - `reports/data_quality_report.json`
   - `reports/checkpoint_coverage.json`
4. **Guardrail run:** dopo ogni refresh registrare una riga in `docs/run_logs.md` usando il template run formalizzato (timestamp/input/output/artifact aggiornati).


## Gate release candidate (obbligatorio)
Prima di aprire o approvare una release candidate eseguire nell'ordine:
1. `python tools/refresh_module_reports.py`
2. `python tools/generate_build_db.py --export-lists --output-dir src/data/builds --modules-output-dir src/data/modules --index-path src/data/build_index.json --module-index-path src/data/module_index.json`
3. Aggiornamento/verifica dei 4 report baseline in `reports/`
4. Registrazione run in `docs/run_logs.md` con stato finale `ok` e artifact elencati

Se il refresh non è stato completato nella stessa finestra temporale della RC, la RC è da considerare bloccata.

## Workstream 1 — Remediation per modulo
1. **Derivare storie di fix**: per ogni modulo, partire dalle osservazioni/errori in `module_work_plan.md` e mantenere l'associazione story → riga sorgente citata.
2. **Implementare e testare**: applicare i fix con riferimento ai file indicati nei report, seguendo le policy di dump/troncamento (`ALLOW_MODULE_DUMP=false` → troncamento con marker) e CTA di export/QA già documentate.
3. **Accettazione**: ogni story richiede evidenza di test (unit/integration) e citazione della riga di `module_work_plan.md` che viene chiusa; aggiornare il tracker e marcare l'item come risolto.

## Workstream 2 — Dipendenze e blocchi
1. **base_profile**: verificare preload dei moduli core e disponibilità del binding nel router prima di rilasciare storie dipendenti; aggiungere nel tracker lo stato (pronto/bloccato) per l'unica dipendenza.
2. **Altri moduli**: se emergono nuove dipendenze durante i fix (es. asset esterni o API chiave), registrarle immediatamente nel tracker e nel changelog del modulo.

## Workstream 3 — QA e sicurezza
1. **Dump/troncamento**: confermare su ogni PR che i comportamenti con `ALLOW_MODULE_DUMP=false` restino invariati (marker di troncamento, header di lunghezza) e che l'export sia bloccato quando richiesto.
2. **Naming export/CTA**: preservare il naming condiviso per gli export (es. `MinMax_<nome>.*`, VTT/MD/PDF in Encounter_Designer) e le CTA di correzione nei gate QA.
3. **Autenticazione**: per gli endpoint protetti (es. `/modules`, `/modules/archivist.txt/meta`), testare 401/403 coerenti con la policy.

## Workstream 4 — Monitoraggio e comunicazione
1. **Tracker sprint**: usare la tabella di chiusura come sorgente di verità per stato/owner; aggiornare lo stato di ogni nota/errore chiuso.
2. **Checkpoint**: mantenere checkpoint periodici (es. giornalieri) per i moduli con più osservazioni (`sigilli_runner_module`, `Encounter_Designer`, `base_profile`), segnalando rischi e regressioni.
3. **Rilascio**: al completamento dei fix, pianificare un regression pass mirato su policy di dump, gating QA e export naming prima di dichiarare "Done" l'intero pacchetto.
