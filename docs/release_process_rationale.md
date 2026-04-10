# Perché mantenere i passaggi di rilascio anche in un team ridotto

Anche quando il ciclo di rilascio è seguito da sole due persone (ad esempio un owner e un assistente), i passaggi strutturati restano utili perché:

- **Tracciabilità e audit**: il messaggio nel canale di rilascio con changelog, log `pytest` e attestato crea una prova consultabile che descrive cosa è stato validato e quando.
- **Punto di verità per il commit RC**: il tag/branch `rc/<data>` lega l’attestato a un commit preciso, evitando dubbi su quale build sia stata approvata.
- **Riduzione del debito operativo**: documentare il messaggio e aggiornare la timeline nel tracker elimina la necessità di ricostruire a posteriori chi ha dato l’ok e con quali evidenze.
- **Resilienza**: se uno dei due non è disponibile, le informazioni minime per proseguire (log QA, attestato, riferimenti) sono già pubblicate e reperibili.
- **Allineamento futuro**: mantenere lo schema ora evita di dover reintrodurre in emergenza il processo quando il team crescerà o servirà una verifica esterna.

Riassunto operativo:
1. Condividere la nota di rilascio nel canale (changelog, log `pytest` 11/12, attestato automatico) e raccogliere feedback/ok.
2. Creare il tag/branch `rc/<data>` dopo attestato verde, come riferimento immutabile.
3. Aggiornare la timeline del tracker con data di pubblicazione e link al messaggio per preservare la storia del rilascio.

## Checklist pre-merge unificata (obbligatoria)

Usare questa checklist unica prima di ogni merge (allineata con `planning/roadmap.md`):

- [ ] **Gate indice↔filesystem bloccante in CI**: `pytest tests/test_module_index.py -q` deve risultare verde.
- [ ] **Aggiornamento artifact dati obbligatorio**: se la PR tocca file in `src/data/`, devono essere aggiornati nello stesso branch anche:
  - `reports/build_review.json`
  - `reports/index_analysis.json`
  - `src/data/module_index.json`
- [ ] **Evidenza QA delta release**: aggiornare `reports/qa_log.md` con sezione **Delta release** (file cambiati + impatto su moduli/build/schema).
- [ ] **Razionale release allineato**: mantenere coerenti note di rilascio, timeline e stato RC (`rc/<data>`).

### Automazione minima per questi tre passi
Usa `tools/release_helper.py` per generare in locale il messaggio e aggiornare la timeline (resta solo da postare manualmente nel canale):

```bash
python tools/release_helper.py \
  --date 2025-12-21 \
  --rc-status "Da creare (dopo attestato verde)" \
  --feedback "TODO dopo pubblicazione"
```

Output generato:
- `reports/release_announcement_<data>.md`: testo da incollare nel canale di rilascio con changelog, stato tag/branch RC, log `pytest` 11/12 e attestato automatico.
- `reports/release_timeline.md`: timeline aggiornata con riferimenti al messaggio e spazio per annotare feedback/approvazioni ricevute.
