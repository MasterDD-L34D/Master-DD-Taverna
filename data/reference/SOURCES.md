# Cataloghi reference — origine e licenza

Questo documento traccia origine, licenza e stato di audit dei cataloghi reference in `data/reference/`.

## Legenda

| Colonna | Significato |
|---------|-------------|
| `catalog` | Nome del file JSON. |
| `origin` | Fonte dati e processo di creazione. |
| `license` | Licenza applicabile al contenuto. |
| `source_publisher` | Chi pubblica il materiale originale. |
| `import_date` | Data creazione/aggiornamento. |
| `entries_count` | Voci attuali. |
| `fields_stored` | Campi conservati per voce. |
| `pi_stripping` | Cosa è stato rimosso/anonimizzato per evitare Product Identity. |
| `notes` | Azioni pendenti o caveat. |

## Cataloghi

| catalog | origin | license | source_publisher | import_date | entries_count | fields_stored | pi_stripping | notes |
|---------|--------|---------|------------------|-------------|---------------|---------------|--------------|-------|
| `spells.json` | Pathfinder 1E RAW/SRD snapshot curato offline + arricchimento con descrizioni da spell gist OGL | OGL 1.0a | Paizo Inc. / d20PFSRD | 2026-07-16 | 1035 | `source_id`, `name`, `source`, `tags`, `prerequisites`, `references`, `reference_urls`, `description` | — | 1032/1035 voci arricchite con `description` via `tools/enrich_reference.py`. |
| `feats.json` | Pathfinder 1E RAW/SRD snapshot curato offline + arricchimento con descrizioni da PFRPG_Feat_card (OGL) | OGL 1.0a | Paizo Inc. / d20PFSRD | 2026-07-16 | 2839 | `source_id`, `name`, `source`, `tags`, `prerequisites`, `references`, `reference_urls`, `description` | — | 2800/2839 voci arricchite con `description` via `tools/enrich_reference.py`; seed bilingue per entry iconiche. |
| `items.json` | Pathfinder 1E RAW/SRD snapshot curato offline + seed manuale per oggetti iconici | OGL 1.0a | Paizo Inc. / d20PFSRD | 2026-07-16 | 257 | `source_id`, `name`, `source`, `tags`, `prerequisites`, `references`, `reference_urls`, `description` | — | 3/257 voci arricchite con `description` via seed bilingue; la maggior parte degli item è in italiano e richiede fonte dedicata. |
| `classes.json` | Generato da `tools/generate_classes_races_archetypes.py` come riassunti meccanici OGL | OGL 1.0a | Paizo Inc. / d20PFSRD | 2026-07-16 | 12 | `source_id`, `name`, `source`, `tags`, `prerequisites`, `references`, `reference_urls`, `notes` | Nessun nome proprio di setting; descrizioni sono riassunti meccanici originali in italiano. | Include 11 classi core + Magus. |
| `races.json` | Generato da `tools/generate_classes_races_archetypes.py` come riassunti meccanici OGL | OGL 1.0a | Paizo Inc. / d20PFSRD | 2026-07-16 | 7 | `source_id`, `name`, `source`, `tags`, `prerequisites`, `references`, `reference_urls`, `notes` | Nessun nome proprio di setting; descrizioni sono riassunti meccanici originali in italiano. | Razze core. |
| `archetypes.json` | Generato da `tools/generate_classes_races_archetypes.py` come riassunti meccanici OGL | OGL 1.0a | Paizo Inc. / d20PFSRD | 2026-07-16 | 15 | `source_id`, `name`, `source`, `tags`, `prerequisites`, `references`, `reference_urls`, `notes` | Nessun nome proprio di setting; descrizioni sono riassunti meccanici originali in italiano. | Archetipi core per Fighter, Wizard, Magus, Rogue, Barbarian, Paladin. |

## Note legali

- I dati meccanici di Pathfinder 1E rientrano in Open Game Content (OGL 1.0a).
- I nomi di razze, classi, archetipi e termini meccanici sono usati in conformità con OGL 1.0a / Community Use Policy di Paizo per uso non commerciale.
- Le descrizioni in `notes` sono riassunti meccanici originali prodotti per questo progetto, non copie testuali da fonti di terze parti.
- I `reference_urls` puntano a d20PFSRD, che è una risorsa OGL-compliant.

## Pipeline di arricchimento

`tools/enrich_reference.py` supporta più fonti:

- `--source seed`: seed manuale bilingue (italiano/inglese) per entry iconiche.
- `--source json`: importa descrizioni dai dataset PFRPG_Feat_card (feats) e Pathfinder Spells Gist (spells).
- `--source scrape`: estrae descrizioni dalle pagine d20pfsrd (richiede `beautifulsoup4` e connessione internet).

Uso consigliato per rigenerare l'arricchimento:

```bash
python tools/enrich_reference.py --source json --kind feats --max-workers 8
python tools/enrich_reference.py --source json --kind spells --max-workers 8
python tools/enrich_reference.py --source seed --kind items
python tools/index_rag.py
```

## Prossimi passi

- Arricchire `items.json` per le voci in italiano/inglese con fonte bulk o scraping d20pfsrd.
- Valutare embeddings multilingue più potenti per migliorare il retrieval cross-lingual.
- Valutare l'espansione con altre classi base (Alchemist, Inquisitor, Summoner, Witch, Gunslinger, Cavalier, Oracle, Summoner, etc.).
- Valutare l'espansione con razze non core (Aasimar, Tiefling, etc.) previo audit PI.
- Valutare l'espansione con archetipi aggiuntivi per ogni classe.
