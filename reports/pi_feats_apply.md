# Applicazione policy PI feats — 2026-07-19

> Generato da `tools/apply_pi_feats_policy.py --write` (Task 2 di `planning/2026-07-19-pi-feats-triage.md`; triage: `reports/pi_feats_triage.md`). Rieseguibile solo dallo stato pre-policy di `feats.json` (guardia fail-closed sui conteggi).

## Conteggi

| Misura | Valore |
| --- | ---: |
| feats.json prima | 2837 |
| feats.json dopo | 2787 |
| feats_local.json | 49 (A=17, B=11, D→A=5, B estesa=16) |
| Ripristini D | 24 (OGL=19, →local=5) |
| Dedup (LastwallPhalanx) | 1 |
| Description sanitize (C + Tattoo Attunement) | 15 |
| Prereq citazione-libro sanitize | 1 |
| Riferimenti a nomi ripristinati corretti | 12 |

## Entry spostate in `pi_local_only/feats_local.json` (49)

Mosse verbatim (A/B e B estesa) o post-ripristino (D→A). File gitignored (pattern `monsters_local.json`): rigenerabile con questo tool dallo stato pre-policy. Indicizzazione RAG: `tools/index_rag.py --include-local`.

| Entry | Origine |
| --- | --- |
| Aldori Artistry | A (PI nel nome) |
| Aldori Dueling Disciple | A (PI nel nome) |
| Aldori Dueling Mastery | A (PI nel nome) |
| Aldori Style | A (PI nel nome) |
| Aldori Style Aegis | A (PI nel nome) |
| Aldori Style Conquest | A (PI nel nome) |
| Andoren Falconry | A (PI nel nome) |
| Daggermark Lore | A (PI nel nome) |
| Hellknight Aegis | A (PI nel nome) |
| Hellknight Obedience | A (PI nel nome) |
| Hellknight Obsession | A (PI nel nome) |
| Hermean Blood | A (PI nel nome) |
| Lastwall Phalanx | A (PI nel nome) |
| Rahadoumi Exorcist | A (PI nel nome) |
| Taldan Duelist | A (PI nel nome) |
| Thuvian Grenadier | A (PI nel nome) |
| Worldwound Walker | A (PI nel nome) |
| Breaker Of Barriers | B (deita' nei prereq) |
| Channel Endurance | B (deita' nei prereq) |
| Destroy Identity | B (deita' nei prereq) |
| Fearsome Finish | B (deita' nei prereq) |
| Mark Of The Devoted | B (deita' nei prereq) |
| Merciless Rush | B (deita' nei prereq) |
| Nightmare Scars | B (deita' nei prereq) |
| Oath Of The Unbound | B (deita' nei prereq) |
| Riptide Attack | B (deita' nei prereq) |
| Squash Flat | B (deita' nei prereq) |
| Wave Master | B (deita' nei prereq) |
| Erastil's Blessing | D→A (ripristinata, identita' PI) |
| Noble Scion (Taldor Variant) | D→A (ripristinata, identita' PI) |
| Osirionology | D→A (ripristinata, identita' PI) |
| Osiriontologist | D→A (ripristinata, identita' PI) |
| Pathfinder Society Ally | D→A (ripristinata, identita' PI) |
| Deadly Troupe | B estesa (varisian (etnia nei prereq)) |
| Duelist Of The Roaring Falls | B estesa (aldori (prereq: Aldori Dueling Disciple, feat A)) |
| Duelist Of The Shrouded Lake | B estesa (aldori (prereq: Aldori Dueling Disciple, feat A)) |
| Falling Water Gambit | B estesa (aldori (prereq: Aldori Dueling Disciple, feat A)) |
| Friendly Rivalry | B estesa (taldan (etnia nei prereq)) |
| Garen's Discipline | B estesa (aldori (tradizione swordlord nei prereq)) |
| Juju Way | B estesa (mwangi (etnia/religione nei prereq)) |
| Loyal To The Death | B estesa (tian (etnia nei prereq)) |
| Ominous Mien | B estesa (hellknight (ordine nei prereq)) |
| Quah Bond | B estesa (shoanti (prereq vincolante 'human (Shoanti)'; il match 'inner sea' e' solo citazione libro)) |
| Redistributed Might | B estesa (aldori (tradizione swordlord nei prereq)) |
| Ruthless Opportunist | B estesa (chelaxian (etnia nei prereq)) |
| Scion Of The Lost Empire | B estesa (chelaxian, taldan (etnia nei prereq)) |
| Signifer Armor Training | B estesa (hellknight (ordine nei prereq)) |
| Totem Spirit | B estesa (shoanti (prereq vincolante 'Member of a Shoanti tribe')) |
| Triangulate | B estesa (kellid (etnia nei prereq)) |

## Policy B estesa (prerequisito vincolante PI)

Decisione controller 2026-07-19: un prerequisito che lega il feat a etnia/organizzazione/tradizione specifica di Golarion equivale al prerequisito deita'-specifico → `pi_local_only` (stessa policy fail-closed dei traits). **16 entry** spostate (tabella sopra, origine "B estesa"), tutte **verbatim** (description originale pre-sanitize, come A/B: in feats_local la fonte resta integrale).

**Valutazione dei 2 casi con match "inner sea" in prereq** (evidenza: testo prereq reale):

- `Harrowed Summoning` → **resta in OGL**: il prereq è "Harrowed (Pathfinder Campaign Setting: The Inner Sea World Guide 287)" — il match "inner sea" e' solo nella **citazione di libro**, il prereq vincolante e' il feat `Harrowed` (presente nel catalogo OGL). Sanitizzato il testo prereq con il replacement neutro ("...: the inner sea region World Guide 287)").
- `Quah Bond` → **feats_local**: i prereq sono "Totem Spirit (The Inner Sea World Guide 289)" + "human (Shoanti)" — il secondo e' **vincolante d'etnia** (stessa classe di `Loyal To The Death` "Human (Tian)"); inoltre il feat prerequisito `Totem Spirit` e' a sua volta B estesa (cascata policy §5).

## Ripristini da fonte AoN (24)

Fonte: pagine `FeatDisplay.aspx` in cache `data/reference/aon_cache/` (lette il 2026-07-19); la tabella e' committata nel tool. Ripristinati nome, description (flavor + benefit, convenzione catalogo), prerequisites, source/tags, references, reference_urls, source_id. Note applicate:

- Tag fonte AoN strippati dai prerequisiti: `ISM`, `ISWG`, `OA`, `APG`.
- Entry tattoo: alternativa PI `or Varisian Tattoo` scartata dai prerequisiti (feat con nome PI assente dal catalogo OGL; convenzione fail-closed di `enrich_feats`).
- `Elemental Fist` e `Elemental Focus`: il contenuto catalogo proveniva dalla carta **Mythic** (collisione titoli nel dataset storico); ripristinato il blocco base AoN (stessa classe del problema sistemico documentato in appendice al triage, qui in scope perche' entry D).
- `Osirionology`/`Osiriontologist`: nomi composti PI-derived non matchati dal word-boundary (\bOsirion\b non matcha "Osirionology"); classificati A per identita' PI (policy: sanitize del nome vietata).

| Nome corrotto | Nome ripristinato | Destinazione |
| --- | --- | --- |
| a god of the hunt's Blessing | Erastil's Blessing | feats_local (A) |
| an ancient desert kingdomology | Osirionology | feats_local (A) |
| an ancient desert kingdomtologist | Osiriontologist | feats_local (A) |
| an explorers' guild Ally | Pathfinder Society Ally | feats_local (A) |
| Ea bardental Channel | Elemental Channel | OGL |
| Ea bardental Commixture | Elemental Commixture | OGL |
| Ea bardental Fist | Elemental Fist | OGL |
| Ea bardental Focus | Elemental Focus | OGL |
| Ea bardental Jaunt | Elemental Jaunt | OGL |
| Ea bardental Knowledge | Elemental Knowledge | OGL |
| Ea bardental Overload | Elemental Overload | OGL |
| Ea bardental Spell | Elemental Spell | OGL |
| Ea bardental Strike | Elemental Strike | OGL |
| Ea bardental Vigor | Elemental Vigor | OGL |
| Extra Ea bardental Assault | Extra Elemental Assault | OGL |
| Flow Of Ea bardents | Flow of Elements | OGL |
| Greater Ea bardental Focus | Greater Elemental Focus | OGL |
| Impa bardent Focus | Implement Focus | OGL |
| Impa bardent Mastery | Implement Mastery | OGL |
| Incremental Ea bardental Assault | Incremental Elemental Assault | OGL |
| Noble Scion a fading empire | Noble Scion (Taldor Variant) | feats_local (A) |
| Strong Impa bardent Link | Strong Implement Link | OGL |
| Tattoo Attunement | Tattoo Attunement (testo/prereq) | OGL |
| Tattoo Transformation | Tattoo Transformation (testo/prereq) | OGL |

## Riferimenti a nomi ripristinati corretti (12)

Sostituzione esatta del set chiuso dei 22 nomi D nei campi `prerequisites`/`references` delle entry non ripristinate:

- `Djinni Spin` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Djinni Spirit` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Djinni Style` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Efreeti Stance` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Efreeti Style` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Efreeti Touch` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Marid Coldsnap` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Marid Spirit` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Marid Style` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Shaitan Earthblast` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Shaitan Skin` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"
- `Shaitan Style` [prerequisites]: "Ea bardental Fist**" → "Elemental Fist**"

## Dedup

- `LastwallPhalanx` rimosso: duplicato esatto di `Lastwall Phalanx` (artifact di import, description identica verificata); l'originale e' categoria A → feats_local.

## Description sanitize (C + post-ripristino) (15)

Scope chirurgico: solo il campo `description` delle entry C rimaste in OGL (le 16 B estesa si sono spostate verbatim prima della sanitize). Tool word-boundary (`tools/sanitize_reference_pi.py`), idempotenza verificata.

- `Arcane Vendetta`: "Irrisen" → "a winter-locked realm" ×1
- `Careful Speaker`: "Galt" → "a revolution-torn land" ×1
- `Cypher Magic`: "the the inner sea region region" → "the inner sea region" ×1; "the inner sea region" → "the inner sea region" ×1; "Riddleport" → "a pirate port" ×1
- `Eye of the Arclord`: "Nex" → "a mage-ruled realm" ×1
- `Grand Duchy Familiarity`: "Alkenstar" → "a gunpowder city" ×1
- `Nameless One`: "Chelish" → "diabolic" ×1; "Mwangi" → "jungle-born" ×1
- `Scholar`: "the the inner sea region region" → "the inner sea region" ×1; "the inner sea region" → "the inner sea region" ×1
- `Shingle Runner`: "Korvosa" → "a port city" ×1
- `Sirian's Masterstroke`: "an Aldori dueling sword" → "a dueling sword" ×1
- `Supernatural Spy`: "Irrisen" → "a winter-locked realm" ×1
- `Tattoo Attunement`: "Inner Sea" → "the inner sea region" ×1
- `Thunder And Fang`: "Shoanti" → "tribal" ×1
- `Totem Beast`: "Shoanti" → "tribal" ×1
- `Vengeful Banisher`: "the Worldwound" → "a demon-blighted land" ×1
- `Wyvaran Spellcasting`: "the the inner sea region" → "the inner sea region" ×1; "the inner sea region" → "the inner sea region" ×2

## Prereq citazione-libro sanitize (1)

Match PI limitato alla citazione di libro (caso non vincolante, § Policy B estesa): testo prereq sanitizzato con i replacement neutri del set base (mai i description-only):

- `Harrowed Summoning`: ['Harrowed (Pathfinder Campaign Setting: The Inner Sea World Guide 287)'] → ['Harrowed (Pathfinder Campaign Setting: the inner sea region World Guide 287)']

## Riferimenti OGL → entry locali (0)

Con la B estesa, la catena duelist (3 riferimenti esatti verso `Aldori Dueling Disciple`, documentati nella prima applicazione) si e' spostata a sua volta in feats_local: i riferimenti sono ora **local→local**. Nessun riferimento esatto residuo da entry OGL a entry locali (verifica `_dangling_refs` sullo stato finale).

## Residui PI: 0

Scansione word-boundary finale (lista 75 termini del triage) su `feats.json`, campi **name + description + prerequisites**: **0 residui** (mascherando i replacement sanctioned come "the inner sea region"). La guardia 5c del tool fallisce l'applicazione se compare qualsiasi residuo nei prerequisites.

## Follow-up (fuori scope, documentati)

- Corruzione sistemica delle description (~75 entry, appendice del triage: "ea bardental", "setta bardent", ...): ripristino sistematico da fonte come task dedicato di data-quality.
- Prefisso references "Archives of a deity of magic" in tutto il catalogo (l'ordine delle regole nel tool e' corretto da questo task; la migrazione dei dati esistenti resta follow-up).
- Campi `source`/`tags` con testo da sanitize storica (es. "the inner sea region Gods"): le entry A/B e B estesa sono state spostate verbatim in feats_local e il ripristino D ha corretto solo le 24 entry interessate; la migrazione globale resta follow-up (stessa classe sistemica). **Fix quality review 2026-07-19**: i campi source/tags delle 24 entry ripristinate sono allineati alla convenzione sanitize del catalogo ("the inner sea region Gods"/"Races", source_id con slug originale), come le altre entry da quei libri.
- `source`/`tags` con citazioni di libri PI mai sanitize in origine (es. "Path Of The Hellknight", presente identico in HEAD su 8 entry OGL residue): classe preesistente fuori scope dei fix, rilevata dalla scansione estesa ai tags; da valutare nel gate di Task 3.
- Tag `**` residui nei prerequisiti (es. "Elemental Fist**"): artifact di import preesistente, non PI.

