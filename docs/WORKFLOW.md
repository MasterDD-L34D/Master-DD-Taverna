# WORKFLOW — come lavoriamo su Master-DD-Taverna

> Metodo consolidato nelle sessioni 2026-07-18/19 (lotti 1-4, Fasi 1-3, feat effects). Da leggere insieme a `AGENTS.md` (regole del repo) e `docs/IMPORT_PLAYBOOK.md` (metodo per gli import dati). Per il contesto cross-repo: `tooling/pathmaster-dd/docs/superpowers/`.

---

## 1. Il ciclo di lavoro (lotto)

1. **Analisi** — gap reale misurato (codice, dati, test), mai assunto. Deliverable: cosa promette vs cosa fa.
2. **Piano TDD completo** (`writing-plans`): task bite-sized con **codice completo in ogni step** (niente placeholder), file esatti, comandi con output atteso, self-review prima di presentarlo. Piani in `planning/YYYY-MM-DD-<feature>.md`, committati.
3. **Esecuzione subagent-driven**: per OGNI task, un implementer fresco (contesto curato dal controller, niente plan file da leggere — testo completo nel prompt), poi **due review indipendenti**:
   - **Spec review**: l'implementazione corrisponde alla spec? (verifica su file reali, non sul report)
   - **Quality review**: è ben costruita? (test eseguiti, edge case, convenzioni)
   - Fix loop fino ad approvazione; il controller verifica ogni fix (grep + test, non fidarsi del report).
4. **Final review** dell'intero lotto (coerenza end-to-end, use case reale, regressioni, igiene) → fix finali.
5. **Verifica rituale** (sempre, con evidenza fresca): `python launch.py test` → TUTTE LE VERIFICHE OK; `legal_filter` 0; `validate_schemas` 0; YAML-check dei moduli `.txt` toccati; reindice RAG se toccati moduli o dati reference.
6. **Push + handoff**: aggiornare `sessione-2026-07-16/HANDOFF_ATTIVO.md` (timestamp, riga stato, voce completato).

## 2. Le review come rete — cosa hanno trovato davvero

Non cerimonie: ogni lotto recente ha avuto bug veri intercettati solo dalle review indipendenti.

- **Bug di regole (RAW)**: conteggio talenti base sbagliato ai livelli pari (`1 + level//2` invece di `(level+1)//2`); Toughness non scalato oltre lv3; "class level 1st" rifiutato a lv1; Monk senza bonus feat; armature multiple bloccanti; taglia Small ignorata.
- **Bug di dati**: ~75% di attribuzioni fonte errate (equipment); 43+ occorrenze PI Golarion sfuggite al filtro base; prerequisiti autoreferenziali; Knowledge senza cross-ref (case/`(all)`).
- **Bug di test**: test che passano solo con il `.env` locale (fixture non ermetica); valori attesi calcolati male (AC, saves, skill totals); trappole `class` vs `class_` nei draft helper.
- **Bug di documentazione**: docstring che dichiarano il falso dopo una feature (limitazione effetti talenti), elenchi kind non aggiornati, nome file errato (`equipment.json` vs `equipment_mundane.json`).

Regola: **un'implementazione non è "pronta" finché una seconda testa non l'ha verificata su file e comandi reali.**

## 3. Policy commit (hook commit-guard attivo)

- Conventional Commits: `type(scope): subject` ≤ 72 char, minuscolo iniziale, niente punto finale.
- **MAI `Co-Authored-By:`** (bloccato dall'hook, ADR-0011 policy-C).
- **ADR-0011 (adottato il 2026-07-19)**: ogni commit include i trailer
  `Coding-Agent: <agent-id>` e `Trace-Id: <uuidv7>` (l'hook li richiede come warn-only; da oggi sono obbligatori qui perché il repo è infrastruttura di verifica di pathmaster-dd). Commit sempre via `git commit -F <file>`.
- **Mai riscrittura della storia**: la policy vale da adesso in poi; i commit precedenti restano com'erano.

## 4. Il contratto del builder (`src/pc/`)

Il builder deterministico è consumato dall'harness a tre vie di pathmaster-dd come terzo oracolo. Regole di evoluzione:

- **Default che decidono numeri: sempre DICHIARATI** nel codice (commento) e in README/docstring (es. `favored_class_bonus: "hp"` di default, `hp_method: "average"` PFS, euristica ranged `< 30 ft`, floor skill 1, WBL best-effort a lv>1, lista `FINESSE_WEAPONS` curata).
- **Cambi di forma input/output: segnalati** (changelog del modulo + nota in commit body) — un adapter si aggiorna, una rottura silenziosa avvelena l'oracolo.
- **Filosofia: valida-e-boccia, mai aggiustare in silenzio.** Errori bloccanti per input illegali; warning per best-effort dichiarati; niente correzioni silenziose dei draft.
- **Limitazioni sempre esplicite** in docstring + README (cosa il motore NON modella: effetti talenti non in `feat_effects.py`, archetipi, multiclasse, effetti condizionali).

## 5. Punti di contatto cross-repo (pathmaster-dd)

| Canale | Stato | Note |
|---|---|---|
| **Terzo oracolo differenziale** (v1 \| v2 \| builder Taverna) | ✅ ATTIVO (spike 2026-07-19) | Il builder ha trovato 2 bug RAW comuni ai due motori pathmaster (favored class "none", conteggio feat lv1); post-fix i tre concordano sui 7 build confrontabili. Invariante feat-count adottato in entrambi i loro `feat-slots.ts` con credito. Evoluzione contratto 2026-07-19 (commit `a7842e4`): nuovo campo opzionale `spells` nel draft (default `[]`); sheet con chiave `spells` solo se la selezione è non vuota; draft senza `spells` → output invariato. |
| **Leva 2 import** (cataloghi Taverna → `UNMODELED_DATA` v2) | Aperto, basso valore ora | I 2839 feat OGL possono popolare/verificare il perimetro unmodeled. |
| **Chronicle M2-B dizionario campagna** | Futuro | I cataloghi OGL (PI già pulita) come seme vocabolario PF1e. |
| **Regola ground-truth condivisa** | Permanente | Doc = ipotesi; git + SRD = verità. La concordanza a tre NON è correttezza: nei disaccordi si apre il SRD, non si vota a maggioranza. |
| **Copertura oracolo** | 28/28 build | 2026-07-19: 24 razze (lotto esotiche) + 24 classi (lotto classi mancanti) → 28/29 build confrontabili; unica esclusa `paladin_aasimar` (razza Aasimar non importata). Rilancio tre-vie sulle 15 build sbloccate da segnalare a pathmaster-dd (caveat: nomi classe/razza nel corpus non canonici — `arcanist`/`tiefling` minuscoli, "Half Orc"/"Halfelf" — serve normalizzazione nel join). |

## 6. Come si riprende in futuro (checklist)

1. Leggi `sessione-2026-07-16/HANDOFF_ATTIVO.md` (stato corrente) e `AGENTS.md`.
2. Se importi dati: `docs/IMPORT_PLAYBOOK.md` (pattern, trappole, PI, checklist registrazione).
3. Se tocchi il builder: rispetta il contratto in §4; se tocchi `src/modules/`: rituale YAML → reindice → test → handoff.
4. Esegui col ciclo in §1; le review non si saltano; i commit seguono §3.
5. Prima di dichiarare qualcosa "fatto": evidenza fresca del comando di verifica (mai dal report).

---

*Creato il 2026-07-19 dopo l'ingaggio da pathmaster-dd (`docs/superpowers/specs/2026-07-19-handoff-kimi-terzo-oracolo.md`).*
