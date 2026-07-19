# Triage PI feats preesistenti — 2026-07-19

> Generato da `tools/triage_pi_feats.py --write`. Fotografia di `data/reference/ogl/feats.json` (2837 entry) allo stato post-`b9f9d63` (HEAD `364cd15`). Evidenza della decisione policy di `planning/2026-07-19-pi-feats-triage.md`.

## Metodo

- **Lista termini**: 75 termini PI (toponimi/etnie/deita'/organizzazioni Golarion-specifici), match **word-boundary** case-insensitive su un'unica regex. Il boundary e' obbligatorio: senza, "Nex" matcha "next" (motivo dei 227 falsi positivi della prima scansione grezza). Criterio di completezza e sweep in § Copertura della lista.
- **Campi scansionati**: `name`, `prerequisites`, `description`.
- **Categorie** (in conflitto vince la piu' severa, D > A > B > C):
  - **A** — match PI nel nome: identita' PI → `pi_local_only` (sanitize del nome vietata).
  - **B** — match di una deita' nei prerequisites: prerequisito deita-specifico → `pi_local_only`.
  - **C** — match solo in description, o PI non-deita' nei prerequisites → sanitize in place.
  - **D** — artifact da sanitize storica naive (nomi corrotti, residui ISM/ISWG, pattern "a frontier landn") → ripristino da fonte, poi ricategorizzazione.
- **Dangling refs**: match esatto case-insensitive del nome entry sugli elementi di `prerequisites`/`references` delle altre entry (convenzione analoga a quella di `parse_skill` per gli header skill, in `tools/import_reference.py`). I riferimenti *embedded* (tag incollati tipo `FeatAPG`, separatori `**`) sono segnalati a parte: non emergono con il match esatto.

## Conteggi

| Categoria | Entry | Destinazione policy |
| --- | ---: | --- |
| A — PI nel nome | 17 | `pi_local_only/feats_local.json` |
| B — deita' nei prerequisites | 11 | `pi_local_only/feats_local.json` |
| C — solo description / prereq non-deita' | 32 | sanitize in place |
| D — artifact sanitize storica | 24 | ripristino → ricategorizzazione |
| **Totale righe triage** | **84** | |

**Confronto con la misura di riferimento (41)**: la misura del controller usava la lista a 54 termini. Con la lista estesa a **75 termini** (quality review 2026-07-19, § Copertura della lista) le entry con almeno un match lessicale salgono a **61** (+20, tutte da termini aggiunti). A queste il triage aggiunge **23 entry di categoria D** il cui nome, corrotto dalla sanitize storica, non contiene piu' alcun termine PI e sfugge quindi al match lessicale (es. "Ea bardental Channel", in origine "Elemental Channel"). Totale righe in triage: 61 + 23 = **84**. Dettaglio in § Note e scarti.

## Copertura della lista

**Criterio di completezza**: un termine entra in lista se e' un toponimo / etnia / deita' / organizzazione **specifico di Golarion** (fonte canonica: AoN/indice feats in cache), con match word-boundary case-insensitive, e ogni hit e' verificato a mano contro falsi positivi prima dell'inclusione. La lista vive in un punto solo (`PI_TERMS` nel tool); Task 3 la unifichera' con `legal_filter.py`.

**Estensione 2026-07-19** (quality review): 17 termini mandati (Lastwall, Worldwound, Belkzen, Shoanti, Mwangi, Tian, Varisian, Chelish, Irrisen, Galt, Hermea, Alkenstar, Korvosa, Riddleport, Daggermark, River Kingdoms, Walkena) + 4 da sweep verificato (**Hermean** — necessario per `Hermean Blood`, \bHermea\b non matcha "Hermean"; **Kellid**, **Mzali**, **Vudra**). Walkena entra anche in `DEITY_TERMS` (deita' Mwangi → categoria B).

**Sweep eseguito**: ~60 candidati (toponimi Inner Sea e oltre, etnie, deita' minori, demon lord, archdevil) cercati word-boundary su `feats.json`. A **zero hit nei campi scansionati** (name/prerequisites/description) del catalogo corrente (non in lista; candidati naturali per il gate di Task 3 i toponimi sicuri): Magnimar, Nirmathas, Molthune, Brevoy, Sandpoint, Cassomir, Ostenso, Westcrown, Egorian, Almas, Sothis, Mendev, Sarkoris, Vudran, Jalmeray, Iobaria, Kalabuto, Bloodcove, Eleder, Usaro, Garund, Avistan, Mbeke, Taralu, Azlant, Thassilon, Xin, Aroden; demon lord/archdevil: Deskari, Baphomet, Pazuzu, Nocticula, Zura, Cyth-V'sug, Moloch, Belial, Dispater, Mammon, Geryon, Baalzebul, Mephistopheles (nomi anche mitologici generici: a maggior ragione fuori dalla lista corrente, rischio FP in altri cataloghi/testi). Nota: **Sargava** ha hit solo nei metadati `source`/`source_id` (titolo del libro "Sargava, The Lost Colony" di 5 entry), zero nei campi scansionati: non in lista.

**Falsi positivi scartati** (hit verificati a mano, termine NON aggiunto):
- **Shackles** — 5 hit, tutti il sostantivo comune "catene" (`Falcon's Cry` "shackles of oppression", `Free Spirit` e `Heroic Will` "mental shackles", `Hellish Shackles` "shackles of Hell", `Liberator` "in shackles"), mai la nazione pirata "The Shackles".
- **Linnorm** — 3 hit (`Linnorm Style`, `Linnorm Vengeance`, `Linnorm Wrath`): tipo di creatura (drago norreno), non il regno dei Linnorm Kings.
- **Juju** — 3 hit: termine ambiguo (parola d'uso comune inglese + creatura "juju zombie" in `Improved Death-Stealing`). Le entry della religione Mwangi restano coperte dai termini gia' in lista: `Juju Way` via "Mwangi" (prereq), `Mark Of The Devoted` via "Mwangi"/"Walkena"/"Mzali". `Improved Death-Stealing` (prereq creatura Nabasu) non e' PI-identity: esclusa.
- **Tian** — mantenuto: etnia canonica di Golarion; il word-boundary protegge dai match dentro altre parole (nessun FP osservato).

## Categoria A — PI nel nome (17)

**Azione proposta (tutta la categoria)**: Spostamento in `pi_local_only/feats_local.json` (identita' PI nel nome; sanitize del nome vietata).

| Entry | Match (campi) | Dangling refs |
| --- | --- | --- |
| Aldori Artistry | name: aldori<br>prereq: aldori<br>desc: aldori | — |
| Aldori Dueling Disciple | name: aldori<br>prereq: aldori<br>desc: aldori | Duelist Of The Roaring Falls [prerequisites] (nel triage: si sposta anch'essa)<br>Duelist Of The Shrouded Lake [prerequisites] (nel triage: si sposta anch'essa)<br>Falling Water Gambit [prerequisites] (nel triage: si sposta anch'essa) |
| Aldori Dueling Mastery | name: aldori<br>prereq: aldori<br>desc: aldori | — |
| Aldori Style | name: aldori<br>prereq: aldori<br>desc: aldori | Aldori Style Aegis [prerequisites] (nel triage: si sposta anch'essa)<br>Aldori Style Conquest [prerequisites] (nel triage: si sposta anch'essa) |
| Aldori Style Aegis | name: aldori<br>prereq: aldori<br>desc: aldori | Aldori Style Conquest [prerequisites] (nel triage: si sposta anch'essa) |
| Aldori Style Conquest | name: aldori<br>prereq: aldori<br>desc: aldori | — |
| Andoren Falconry | name: andoren<br>desc: andoren | — |
| Daggermark Lore | name: daggermark<br>prereq: daggermark<br>desc: daggermark, river kingdoms | — |
| Hellknight Aegis | name: hellknight<br>prereq: hellknight<br>desc: hellknight | — |
| Hellknight Obedience | name: hellknight<br>prereq: hellknight<br>desc: hellknight | Hellknight Obsession [prerequisites] (nel triage: si sposta anch'essa) |
| Hellknight Obsession | name: hellknight<br>prereq: hellknight<br>desc: hellknight | — |
| Hermean Blood | name: hermean<br>desc: hermea, hermean | — |
| Lastwall Phalanx | name: lastwall<br>desc: belkzen | — |
| Rahadoumi Exorcist | name: rahadoumi<br>desc: rahadoumi | — |
| Taldan Duelist | name: taldan | — |
| Thuvian Grenadier | name: thuvian | — |
| Worldwound Walker | name: worldwound | — |

## Categoria B — deita' nei prerequisites (11)

**Azione proposta (tutta la categoria)**: Spostamento in `pi_local_only/feats_local.json` (prerequisito deita-specifico).

| Entry | Match (campi) | Dangling refs |
| --- | --- | --- |
| Breaker Of Barriers | prereq: rovagug | — |
| Channel Endurance | prereq: gozreh | — |
| Destroy Identity | prereq: lamashtu | — |
| Fearsome Finish | prereq: lamashtu | — |
| Mark Of The Devoted | prereq: mwangi, walkena<br>desc: mzali | — |
| Merciless Rush | prereq: rovagug | Squash Flat [prerequisites] (nel triage: si sposta anch'essa) |
| Nightmare Scars | prereq: lamashtu<br>desc: lamashtu | — |
| Oath Of The Unbound | prereq: rovagug | — |
| Riptide Attack | prereq: gozreh | — |
| Squash Flat | prereq: rovagug | — |
| Wave Master | prereq: gozreh<br>desc: gozreh | — |

## Categoria C — match solo in description / prereq non-deita' (32)

**Azione proposta (tutta la categoria)**: Sanitize in place dei campi description/prerequisites (tool word-boundary, Task 2); nessuno spostamento.

| Entry | Match (campi) | Dangling refs |
| --- | --- | --- |
| Arcane Vendetta | desc: irrisen | — |
| Careful Speaker | desc: galt | — |
| Cypher Magic | desc: inner sea, riddleport | — |
| Deadly Troupe | prereq: varisian | — |
| Duelist Of The Roaring Falls | prereq: aldori<br>desc: aldori | — |
| Duelist Of The Shrouded Lake | prereq: aldori<br>desc: aldori | — |
| Eye of the Arclord | desc: nex | — |
| Falling Water Gambit | prereq: aldori<br>desc: aldori | — |
| Friendly Rivalry | prereq: taldan | — |
| Garen's Discipline | prereq: aldori | — |
| Grand Duchy Familiarity | desc: alkenstar | — |
| Harrowed Summoning | prereq: inner sea | — |
| Juju Way | prereq: mwangi<br>desc: mwangi | — |
| LastwallPhalanx | desc: belkzen | — |
| Loyal To The Death | prereq: tian | — |
| Nameless One | desc: chelish, mwangi | — |
| Ominous Mien | prereq: hellknight<br>desc: hellknight | — |
| Quah Bond | prereq: inner sea, shoanti<br>desc: shoanti | — |
| Redistributed Might | prereq: aldori | — |
| Ruthless Opportunist | prereq: chelaxian<br>desc: chelish | — |
| Scholar | desc: inner sea | — |
| Scion Of The Lost Empire | prereq: chelaxian, taldan | — |
| Shingle Runner | desc: korvosa | — |
| Signifer Armor Training | prereq: hellknight<br>desc: hellknight | — |
| Sirian's Masterstroke | desc: aldori | — |
| Supernatural Spy | desc: irrisen | — |
| Thunder And Fang | desc: shoanti | — |
| Totem Beast | desc: shoanti | — |
| Totem Spirit | prereq: shoanti<br>desc: shoanti | — |
| Triangulate | prereq: kellid | — |
| Vengeful Banisher | desc: worldwound | — |
| Wyvaran Spellcasting | desc: inner sea | — |

## Categoria D — artifact da sanitize storica (24)

**Azione proposta (tutta la categoria)**: Ripristino da fonte (cache AoN / re-import), poi ricategorizzazione A/C.

| Entry (stato corrente) | Artifact | Ripristino proposto | Dangling refs |
| --- | --- | --- | --- |
| a god of the hunt's Blessing | name: nome corrotto: contiene 'a god of the hunt's' (replacement sanitize) | Erastil's Blessing | — |
| an ancient desert kingdomology | name: nome corrotto: contiene 'an ancient desert kingdom' (replacement sanitize) | Osirionology | — |
| an ancient desert kingdomtologist | name: nome corrotto: contiene 'an ancient desert kingdom' (replacement sanitize) | Osiriontologist | — |
| an explorers' guild Ally | name: nome corrotto: contiene 'an explorers' guild' (replacement sanitize) | Pathfinder Society Ally | — |
| Ea bardental Channel | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Channel | — |
| Ea bardental Commixture | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Commixture | — |
| Ea bardental Fist | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Fist | Djinni Spin [prerequisites, embedded: `Ea bardental Fist**`]<br>Djinni Spirit [prerequisites, embedded: `Ea bardental Fist**`]<br>Djinni Style [prerequisites, embedded: `Ea bardental Fist**`]<br>Efreeti Stance [prerequisites, embedded: `Ea bardental Fist**`]<br>Efreeti Style [prerequisites, embedded: `Ea bardental Fist**`]<br>Efreeti Touch [prerequisites, embedded: `Ea bardental Fist**`]<br>Marid Coldsnap [prerequisites, embedded: `Ea bardental Fist**`]<br>Marid Spirit [prerequisites, embedded: `Ea bardental Fist**`]<br>Marid Style [prerequisites, embedded: `Ea bardental Fist**`]<br>Shaitan Earthblast [prerequisites, embedded: `Ea bardental Fist**`]<br>Shaitan Skin [prerequisites, embedded: `Ea bardental Fist**`]<br>Shaitan Style [prerequisites, embedded: `Ea bardental Fist**`] |
| Ea bardental Focus | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Focus | Greater Ea bardental Focus [prerequisites] (nel triage: si sposta anch'essa) |
| Ea bardental Jaunt | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Jaunt | — |
| Ea bardental Knowledge | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Knowledge | — |
| Ea bardental Overload | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Overload | — |
| Ea bardental Spell | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Spell | — |
| Ea bardental Strike | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Strike | — |
| Ea bardental Vigor | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Elemental Vigor | — |
| Extra Ea bardental Assault | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Extra Elemental Assault | — |
| Flow Of Ea bardents | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Flow of Elements | — |
| Greater Ea bardental Focus | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Greater Elemental Focus | — |
| Impa bardent Focus | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Implement Focus | — |
| Impa bardent Mastery | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Implement Mastery | — |
| Incremental Ea bardental Assault | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Incremental Elemental Assault | — |
| Noble Scion a fading empire | name: nome corrotto: contiene 'a fading empire' (replacement sanitize) | Noble Scion (Taldor Variant) | — |
| Strong Impa bardent Link | name: nome corrotto: contiene 'a bard' (replacement sanitize) | Strong Implement Link | — |
| Tattoo Attunement | prerequisites: residuo tag fonte 'TattooISM' | — (ripristino testo, nome intatto) | Tattoo Conversion [prerequisites, embedded: `Inscribe Magical Tattoo; Tattoo Attunement; Spellcraft 15 ra`] |
| Tattoo Transformation | prerequisites: residuo tag fonte 'TattooISM' | — (ripristino testo, nome intatto) | — |

## Riferimenti pendenti (dangling refs) — dettaglio

Nessun riferimento esatto pendente: tutti i riferimenti esatti ad entry A/B/D provengono da entry a loro volta nel triage (si spostano/sanitizzano insieme).

Riferimenti **embedded** (non esatti: tag fonte incollati o separatori `**`; il match esatto della policy non li vede — rilevanti per il ripristino dei nomi D):

- `Djinni Spin` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Djinni Spirit` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Djinni Style` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Efreeti Stance` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Efreeti Style` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Efreeti Touch` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Marid Coldsnap` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Marid Spirit` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Marid Style` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Shaitan Earthblast` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Shaitan Skin` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Shaitan Style` → `Ea bardental Fist` (campo `prerequisites`: "Ea bardental Fist**")
- `Tattoo Conversion` → `Tattoo Attunement` (campo `prerequisites`: "Inscribe Magical Tattoo; Tattoo Attunement; Spellcraft 15 ranks; ability to cast")

## Appendice — corruzione sistemica delle description (fuori scope triage PI)

La sanitize storica naive ha sostituito i nomi degli iconici ("Lem" → "a bard", ecc.) **dentro le parole**: "elemental" → "ea bardental", "settlement" → "setta bardent", "implement" → "impa bardent", "golems" → "goa bards", "Arcanamirium" → "Arcana barbarianum". Oltre alle entry D gia' in tabella, **75 entry** (senza rilevanza PI: nessun match di termine, nome intatto) hanno description/prerequisites/references corrotti da questa classe. Non entrano nella decisione policy A/B/C ma sono evidenza per un ripristino sistematico delle description da fonte (decisione del controller: estensione Task 2 o task dedicato).

Stessa classe, nei `references` di quasi tutto il catalogo: "Archives of a deity of magic" — il replacement "Nethys" → "a deity of magic" e' applicato **prima** di "Archives of Nethys" → "Pathfinder PRD" nell'ordine di `REPLACEMENTS`, quindi la regola frase-level non scatta mai. Non e' corruzione del contenuto (solo riferimento fonte), ma va corretta nell'ordine delle sostituzioni del tool sanitize (Task 2).

<details><summary>Elenco entry (nomi)</summary>

Agonizing Obedience, Airy Step, Aspiringnoble, Aspis Partner, Associate, Bend With The Wind, Black Market Dealings, Blasting Charge, Brilliant Planner, Call Truce, Chakra Adept, Chakra Initiate, Chakra Mandala, Chakra Master, Charging Stag Style, City-Locked, Cloud Gazer, Craft Construct, Cranial Implantation, Criminal Reputation, Demonic Obedience, Djinni Spin, Djinni Spirit, Djinni Style, Draconic Manifestation, Efficient Focus Shift, Efreeti Stance, Efreeti Style, Efreeti Touch, Extend Resonant Power, Extra Focus Power, Extra Wild Talent, Eye For Ingredients, False Casting, Favored Community, Foeslayer, Fortunate Ruler, Greater Wild Empathy, Guild Emissary, Harvest Parts, Hindrance Dismissal, Implant Bomb, Improved Familiar, Inner Breath, Ironclad Logic, Kinetic Counter, Kinetic Crafting, Kinetic Invocation, Manifested Blood, Marid Coldsnap, Marid Spirit, Marid Style, Metamagic Invocation, My Blade Is Yours, Prosperity And Pride, Protector Of The People, Rapid Focus Shift, Renown, Scorching Weapons, Shaitan Earthblast, Shaitan Skin, Shaitan Style, Shrug On, Spell Bluff, Steam Caster, Storm-Lashed, Stunning Irruption, Surface Scout, Threatening Illusion, Touched By Sacred Fire, Town Tamer, Triton Portal, Underworld Connections, Whispering Way Disciple, Wretched Curator

</details>

## Note e scarti rispetto al piano

- **Scarto conteggio**: la misura di riferimento del controller (41) contava i match lessicali word-boundary della lista a 54 termini; il triage li riproduce esattamente (le 20 entry aggiunte ai match lessicali provengono tutte dai 21 termini dell'estensione quality review, § Copertura della lista) e vi aggiunge le entry D senza match lessicale residuo (nomi corrotti da "Lem"→"a bard", "Osirion"→"an ancient desert kingdom", "Erastil's"→"a god of the hunt's", "Pathfinder Society"→"an explorers' guild"). Il tool ha ragione: lo scarto e' ri-derivato riga per riga nelle tabelle sopra.
- **Ricategorizzazioni rispetto alla stima preliminare del piano**:
  - `Eye of the Arclord`: match "Nex" in description (non nel nome) → **C**, come previsto dal piano ("verificare").
  - `Noble Scion a fading empire`: il piano la citava tra i nomi A; avendo artifact nel nome e' **D** (vince la piu' severa). Ripristino proposto: "Noble Scion (Taldor Variant)" (nome AoN da indice in cache; il piano citava "Noble Scion of Taldor", forma d20pfsrd — confermare su fonte in Task 2).
  - I feat delle famiglie Aldori/Hellknight **senza** il termine nel nome letterale (`Duelist Of The Roaring Falls`, `Ominous Mien`, `Signifer Armor Training`, ecc. — il piano li elencava nel bucket A per famiglia) ricadono in **C** per la regola stretta "A = match nel nome". Nota policy: la loro description/prereq contiene il termine PI e i prereq referenziano feat A in partenza (vedi dangling refs): valutare in Task 2 se trattarli come famiglia (spostamento a cascata, policy §5) invece che sanitize C.
- **Residui ISM**: `b9f9d63` ha pulito "a frontier landn" e "TattooISWG", ma resta "Inscribe Magical TattooISM" (tag ISM incollato) nei prerequisites di `Tattoo Attunement` e `Tattoo Transformation` → **D** (ripristino testo; post-ripristino escono dal triage: nessun PI).
- **Raddoppi da sanitize parziale**: alcune C con "inner sea" (es. `Scholar`: "throughout the the inner sea region region") sono gia' state sanitize una volta in modo naive ("Inner Sea region" → "the inner sea region region") e contengono ancora il termine. La sanitize word-boundary di Task 2 deve essere **idempotente**: risostituire "inner sea" dentro "the inner sea region" produrrebbe un'ulteriore incollatura.
- **Falsi positivi esclusi** (documentati nel tool): `Extra Rogue Talent`, `Extra Ranger Trap` (nomi legittimi: "a rogue"/"a ranger" a cavallo di "Extra Rogue|Ranger"); "a bardic performance" (inglese corretto) nell'appendice sistemica. I FP dello sweep termini (Shackles, Linnorm, Juju) sono in § Copertura della lista.
- **Duplicato `LastwallPhalanx`**: entry distinta da `Lastwall Phalanx` con nome incollato (artifact di import, non da sanitize) e description identica. La regola stretta la classifica **C** (match "Belkzen" in description; \bLastwall\b non matcha il nome incollato), ma l'identita' e' PI: in Task 2 valutare dedup + trattamento come `Lastwall Phalanx` (A).
- **Git history non utilizzabile per il ripristino**: la corruzione e' anteriore al primo commit OGL (`596f9df`); i nomi originali proposti sono verificati contro l'indice feats AoN in cache (`data/reference/aon_cache/19b525ecab068e0c.html`, 3446 nomi).

## Verifiche manuali a campione

Campioni verificati a mano contro `feats.json` allo stato fotografato (HEAD `364cd15`, 2026-07-19). Evidenza riproducibile: `python tools/triage_pi_feats.py --write` rigenera deterministicamente questo report dagli stessi dati.

1. **`Aldori Dueling Disciple` (A)**: "Aldori" in name, prereq e description; referenziata esattamente dai prerequisites di `Duelist Of The Roaring Falls`, `Duelist Of The Shrouded Lake`, `Falling Water Gambit` (tutte C: dangling interno al triage).
2. **`Squash Flat` (B)**: "Rovagug" nei prerequisites ("worshiper of Rovagug"); referenzia esattamente `Merciless Rush` (B): dangling interno, si spostano insieme.
3. **`Ea bardental Channel` (D)**: nessun match lessicale; nome con "a bard" (Lem→a bard dentro "Elemental"); originale "Elemental Channel" confermato nell'indice AoN in cache; description con "ea bardental subtype" (stessa corruzione).
4. **`Scholar` (C)**: match "inner sea" solo in description; nessun dangling ref.
5. **`Lastwall Phalanx` (A, estensione)**: "Lastwall" nel nome, "Belkzen" in description; duplicato `LastwallPhalanx` tracciato in § Note.
6. **`Mark Of The Devoted` (B, estensione)**: prereq "Walkena worshiper" (deita' Mwangi) + "human of Mwangi ethnicity"; "Mzali" in description.

