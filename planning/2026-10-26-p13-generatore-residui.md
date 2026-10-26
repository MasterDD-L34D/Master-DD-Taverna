# P13 — Generatore: residui ko/unknown e vincoli RAW (piano)

Data: 2026-10-26. Voce di coda: `CODA_LAVORI.md` P13 (eredita P12-d,
rapporto `pathmaster-dd/docs/p12d-rapporto-finale-2026-10-20.md`).
Rampe: questo branch (`kimi/generatore-armatura-non-competente`).

## Contesto misurato (sonda-noncompetenza di pathmaster-dd, corpus = questa repo)

Stato alla apertura del cantiere (corpus Taverna, 2026-10-26):

- **10 ko** equipaggiamento non competente + **4 unknown** armi divinita.
- Le tre famiglie (coda P13):
  1. `wizard_elf_universalist` ×6 — "Armatura leggera" inventata dal fallback
     dello stub builder. **Codice già fixato in `17420de`**; il corpus
     conservava la voce stale.
  2. `kineticist_*_kinetic_knight_*` ×4 dichiarati — breastplate/scudo
     pesante prima del gate RAW di livello 2 del grant Kinetic Knight.
  3. 4 unknown — Kukri/Scimitar "arma della divinità": il campo
     `profile.divinita` esiste (`/set_profile`, export lo emette) ma le
     sessioni di generazione non lo hanno popolato per inquisitore/cleric.

**Scoperta del censimento 2026-10-26**: il rebuild delle schede ha schiacciato
a `livelli: 1` tutte le varianti lvl05/lvl10 — **50 file** (25 famiglie × 2)
hanno livelli/statistiche di livello 1; la copia pathmaster-dd (snapshot pre-
rebuild) ha i valori corretti. Campione verificato (kinetic lvl05): TA=CA 14,
attacco +6, DES 16 vs PM=CA 25, attacco +13, DES 20. Non sono duplicati del
file base: sono schede riscritte male. Questo gonfia i ko della famiglia 2
(da 4 file veri a 8 voci) e invalida qualunque misura a valle sulle build di
livello.

## Fette

### P13-1 — cura corpus wizard ✅ FATTA (2026-10-26, `f4ac978`)

`tools/cura_armatura_stub_wizard.py`: rimuove la voce dalle 6 build (live +
archive, tutte le copie annidate), dichiara in `_normalized.curaArmaturaStub`,
verifica la derivazione contro `build_stub_payload` (fallisce senza scrivere).
Gate: pytest 709 passed, validate_schemas 0, data_quality_report 0.
Misura a valle: **10 ko → 8**, famiglia wizard a zero.

### P13-2 — restauro delle 50 schede di livello schiacciate

Ripristinare in `src/data/builds/` le 50 varianti lvl05/lvl10 dal snapshot
pathmaster-dd (`data/reference/builds/`, copia pre-rebuild), preservando le
dichiarazioni `_stripped`/`_normalized` gia' presenti nei file Taverna.
Verifica a valle: sonda-noncompetenza su corpus Taverna attesa **8 → 4 ko**
(knight base live + archive, i lvl05/10 tornano legali col gate livello 2)
e launch.py test verde. Attenzione al rituale AGENTS.md (pytest e' lento,
~4,5 min; gli 8 skipped ML sono ambientali).

### P13-3 — vincoli nel modulo minmax_builder (generazione futura) ✅ FATTA (2026-10-26)

Tre vincoli in `constraints:` (versione 5.3), poi reindice RAG eseguita:
1. **Checklist competenza equipaggiamento**: prima di `/add_item` di
   armature/scudi, verifica competenza classe+archetipo+talenti; se non
   competente, dichiarare il ko nella build invece di inserire in silenzio
   (il silenzio della fonte non autorizza oggetti con ACP).
2. **Gate di livello dei grant d'archetipo**: l'equipaggiamento concesso da
   un grant gated (es. Kinetic Knight liv 2) entra solo quando il gate e'
   raggiunto; sotto, segnalato come disponibile-futuro.
3. **Divinita obbligatoria per classi dipendenti** (inquisitore, chierico,
   warpriest, paladino...): `/set_profile` deve popolare `divinita` prima
   dell'export; l'export gia' emette il campo — manca il vincolo di flusso.

## Criterio di uscita (board agenti)

Corpus rigenerato/curato su cui `tools/sonda-noncompetenza.mts`
(pathmaster-dd, `MASTER_DD_BUILDS_DIR` puntato qui) riporta **0 ko + 0
unknown**. La verifica a valle la esegue la sponda pathmaster perche' la
sonda vive li. Le 4 unknown divinita esistenti richiedono la divinita
scelta nelle sessioni originali (owner) o restano dichiarate.
