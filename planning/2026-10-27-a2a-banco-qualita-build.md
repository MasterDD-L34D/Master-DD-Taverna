# Piano A2-a — Banco qualita' build: ricalcolo meccanico con src/pc (v2)

Data: 2026-10-27 · Sponda: kimi · Direzione A (chiudere MOD-LLM) · Fetta A2-a
Stato: v2 dopo review Claude giro 1 (3 P1 + 4 P2 + 4 P3, tutti recepiti)
IN ATTESA DI RATIFICA OWNER

## Contesto

La "lacuna onesta" (qualita' delle risposte mai misurata) e' confermata in
`src/agents/builder.py` (520 righe): il Build Agent valida solo
**plausibilita'** (schema, source_id esistenti, numeri vs benchmark con
tolleranze larghe x2/+10/x3). Nessun ricalcolo meccanico delle statistiche
dichiarate dal LLM.

Risorsa in casa: `src/pc/engine.py` `build_character(CharacterDraft)`
calcola a livelli 1-20: hp, saves, bab, skills, CA e attacchi da equip
(`attacks`: bonus + dado danno, NON danno atteso/DPR).

Review Claude giro 1 (rilievi recepiti in questa v2):
- **P1** il banco sul fallback e' tautologico (verde per costruzione) — la
  baseline di qualita' vera deve venire da fixture LLM registrate, il mock
  serve solo da smoke del codice del banco;
- **P1** `sheet` e' gia' usata con altro significato (`stub_builder.py`,
  `tests/test_app.py` chiavi italiane; `generate_build_db.py` la
  sovrascrive con `sheet_markdown`) — si usa una chiave NUOVA `pc_draft`;
- **P1** il contratto proposto in v1 non era compatibile con
  `CharacterDraft` — v2 lo rende 1:1;
- **P2** PF esatto irrealistico senza `favored_class_bonus` nel contratto;
  tolleranze +-1 ignorano oggetti magici (WBL lv5 ~10.500 mo) e bonus
  razziali ai TS che l'engine non applica — serve esito
  `non_verificabile`;
- **P2** serve il terzo esito "rifiutato" (l'engine puo' rifiutare la
  bozza: point-buy sforato, classe/razza sconosciuta) e il livello 1 va
  riportato separato (regime di validazione piu' stretto: ricchezza di
  classe, item sconosciuto = errore);
- **P3** corpus con seed fisso (niente scelta a mano dei casi comodi);
  `meta_tier`/tier resta NON verificato e va dichiarato nel report;
  stima a1 raddoppiata; encoding ASCII.

## Decisioni prese (dalla review)

- **D1 — Chiave `pc_draft`**, non `sheet`. `$def` tipizzato aggiunto a
  `build_core.schema.json` (AGGIUNTIVO, non breaking: `sheet` resta
  com'e'). Validazione RED reale su `pc_draft` malformata.
- **D2 — Contratto 1:1 con `CharacterDraft`** (src/pc/models.py):
  chiavi inglesi `str/dex/con/int/wis/cha`, punteggi BASE point-buy (non
  finali — `apply_abilities` somma i bonus razziali, passare i finali
  conta la razza due volte), campi obbligatori `name`/`method`/
  `campaign_type`, `favored_class_bonus` (default "hp" = +1 PF/livello),
  `race_bonus_ability`, `feats` come stringhe `"Weapon Focus
  (Longsword)"`, `equipment` con nomi ESATTI dal catalogo (`find_equipment`
  cerca per nome esatto).
- **D6 — Regola di attribuzione**: il banco riporta, non giudica. Tre esiti
  + non_verificabile; la soglia `exit 1` si fissa solo dopo la prima
  baseline (su fixture LLM, non su mock).

## Fette

### a1 — Popolamento `pc_draft`

- `$def` `pc_draft` in `schemas/build_core.schema.json` (aggiuntivo).
- Prompt (`_make_prompt`): chiede al LLM `pc_draft` 1:1 con
  `CharacterDraft`, nomi solo dal catalogo reference.
- `_build_fallback`: riempie `pc_draft` lui stesso (draft minimo valido
  per classe/razza) — resta sottoposto al banco come smoke.
- Adattatore nomi: LLM tende a minuscole/parziali → risoluzione con
  `_normalize_name` gia' presente, mismatch = `non_verificabile` (mai
  competenza finta nel senso inverso: non attribuire al LLM un buco
  dell'adattatore).

### a2 — Banco ricalcolo (`tools/bench_build_quality.py`)

Per ogni build del corpus:

1. `CharacterDraft.from_dict(payload["pc_draft"] + class/race/level)`;
2. `build_character(draft)` -> sheet ricalcolato;
3. confronto con `payload["benchmark"]["statistics"]`, esiti:
   - `concorda`: PF esatto (con `favored_class_bonus` noto), saves +-1,
     CA +-1;
   - `diverge`: dettaglio per statistica (atteso vs dichiarato);
   - `rifiutato`: l'engine ha respinto la bozza (reportato a parte);
   - `non_verificabile`: oggetti magici fuori catalogo, bonus razziali ai
     TS non applicati dall'engine, mismatch nomi non risolto;
4. report: per statistica e per livello, con **livello 1 separato** dai
   livelli 2-5 (regimi di validazione diversi). Dichiarato: tier/meta_tier
   NON verificato (3 statistiche su 4).

Corpus:
- **smoke** (CI, mock/fallback): codice del banco, matrice ridotta.
- **qualita'** (baseline vera): fixture LLM registrate — risposte reali
  del provider salvate in `tests/fixtures/bench_llm/`, campionate con
  **seed fisso** da classi x razze x livelli 1-5 coperte da
  `src/pc/catalogs.py` (censimento come primo passo di a2: quante
  classi/razze hanno progression+mechanics complete).
- LLM reale (ollama) solo manuale, mai bloccante in CI (D5 invariata).

### a3 — Integrazione gate oracolo (dopo baseline, ratifica separata)

## Gate di fetta

- a1: `$def` validato — `pc_draft` malformata = RED reale su
  `validate_with_schema`; fallback popola `pc_draft`; test dedicati.
- a2: censimento classi/razze; banco su corpus smoke >= 20 build + report
  baseline su fixture; tre esiti + non_verificabile distinti nel report;
  suite di ritorno verde.

## Fuori perimetro

Ricalcolo via oracolo pathmaster-dd (A2-b), DPR (il pc engine produce
attacchi con dado danno, non danno atteso — estensione futura),
modifiche al pc engine per coprire buchi (bonus razziali ai TS, oggetti
magici: SEGNALATI nel report come non_verificabile, non colmati qui),
banco RAG (fermo: nessun bisogno misurato).
