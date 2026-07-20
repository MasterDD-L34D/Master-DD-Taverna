# Applicazione policy PI traits + equipment — 2026-07-19

> Generato da `tools/apply_pi_traits_equipment_policy.py --write`. Estensione della policy PI (decisione controller 2026-07-19) ai debiti preesistenti rilevati dal gate esteso di Task 3 (`tools/legal_filter.py`): stessa disciplina di `reports/pi_feats_apply.md` (A/B -> `pi_local_only`, C -> sanitize description, fail-closed sui conteggi).

## Tabella entry -> destinazione

| Entry | Catalogo | Cat. | Destinazione | Motivo |
| --- | --- | --- | --- | --- |
| Aldori Caution | traits | A | traits_local | "Aldori" nel nome (organizzazione PI) |
| Alkenstar fortress plate | equipment | A | equipment_local | "Alkenstar" nel nome |
| Arodenite Historian | traits | A | traits_local | "Arodenite" nel nome (come sopra) |
| Arodenite Sword Training | traits | A | traits_local | "Arodenite" nel nome (aggettivo della deita' PI; \bAroden\b non matcha il nome, identita' PI per decisione controller) |
| Bureaucrat's Favored | traits | C | sanitize in place | "Sothis" in description -> "a desert metropolis" (regola nuova); prereq "Osiria" -> "an ancient desert kingdom" (set base; fix quality review: requisito di associazione a una corte, il toponimo neutralizzato lascia il requisito coerente — a differenza di "Ostenso" in Gifted Smuggler, unico contenuto del prereq -> B) |
| Crusader | traits | C | sanitize in place | "the Worldwound" in description -> "a demon-blighted land" |
| Divine Denier | traits | C | sanitize in place | "Rahadoumi" in description -> "godless" |
| Dueling Cloak Adept | traits | C | sanitize in place | "an Aldori dueling sword" in description -> "a dueling sword" |
| Gifted Smuggler | traits | B | traits_local | prerequisito vincolante PI: "Ostenso" |
| Hellknight half-plate | equipment | A | equipment_local | "Hellknight" nel nome |
| Hellknight leather | equipment | A | equipment_local | "Hellknight" nel nome |
| Hellknight plate | equipment | A | equipment_local | "Hellknight" nel nome |
| Reassuring Advice | traits | C | sanitize in place | "Aroden" x3 nella stessa description -> "a dead god"; NOTA: 1 sola entry (le 3 occorrenze del gate sono nella stessa description), dedup non applicabile |
| Scholar of the Analects | traits | C | sanitize in place | "Aroden" in description -> "a dead god" (regola nuova) |
| Stabbing Spells | traits | C | sanitize in place | "Aroden" in description -> "a dead god" (regola nuova) |

## Conteggi

- `traits.json`: 470 -> **466** (A=3 + B=1 in `pi_local_only/traits_local.json`; C=7 description sanitize in place).
- `equipment_mundane.json`: 790 -> **786** (A=4 in `pi_local_only/equipment_local.json`).
- Nessun riferimento pendente (check dangling refs su tutti i cataloghi OGL: prerequisites/references).
- Gate post-applicazione: **0 violazioni** su traits ed equipment (scansione `legal_filter._find_pi`, campi scansionati).

## Follow-up (fuori scope, documentati)

- **Titoli libro PI nei campi `source`** (il gate non scansiona `source`; le 8 feats sanitize in Task 3 erano in `tags`, che e' scansionato): equipment "Pirates of the Inner Sea" x10, "Inner Sea Intrigue/Temples/World Guide" x13, "Path of the Hellknight" (Manacles (mithral)); traits "Knights of the Inner Sea" x9, "Path of the Hellknight" (Godclaw Disciple). Decisione separata.
- `reports/pi_feats_triage.md` resta la fotografia storica di feats.json@364cd15: non rigenerato per decisione del controller.

## Fix quality review 2026-07-19 (pre-commit)

- **"Osiria"** nei prerequisites di `Bureaucrat's Favored` ("court of the Black Dome in Osiria"): variante di "Osirion" non coperta dalla lista. Aggiunta ai candidati del gate (`GATE_CANDIDATE_TERMS`) e sanitizzata con la forma neutra della famiglia Osirion ("an ancient desert kingdom", set base). Classificazione confermata C: requisito di associazione a una corte (non etnia/deita' vincolante); il toponimo neutralizzato lascia il requisito coerente.
- **Ritocco grammaticale post-replacement** (2 description, intervento manuale): `Stabbing Spells` "a dead god wrote much..." -> "A dead god wrote much..." (maiuscola a inizio frase); `Divine Denier` "you're a godless objecting" -> "you're a godless one objecting".

