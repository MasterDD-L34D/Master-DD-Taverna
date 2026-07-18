# Checklist PR

Il workflow di QA compila e spunta automaticamente i controlli in base ai risultati dei test: se il job fallisce, controlla i [log del QA workflow](https://github.com/MasterDD-L34D/Master-DD-Taverna/actions/workflows/pr-checklist.yml) e ripeti la verifica.

### Come funziona l'autocompilazione
- Esegui o rilancia i test richiesti; il workflow inserirà automaticamente i risultati e spunterà i controlli.
- Aggiungi manualmente solo eventuali note extra o chiarimenti non coperti dal workflow.

## Controlli obbligatori
- [ ] Test con dump disabilitato (marker/header)
- [ ] Naming export corretto
- [ ] CTA QA presenti
- [ ] 401/403 per endpoint protetti

## Evidenze di test per ciascun controllo
Il workflow aggiorna automaticamente questa tabella: non sostituire i valori a mano, aggiungi solo eventuali note extra sotto la tabella se servono.

<!-- AUTO-QA-START -->
| Controllo | Storia collegata | Tipo di test (unit/integration/manuale) | Evidenza (link/log, includere header/marker rilevante) |
| --- | --- | --- | --- |
| Test con dump disabilitato (marker/header) | In attesa esito workflow | integration | In esecuzione... |
| Naming export corretto | In attesa esito workflow | static | In esecuzione... |
| CTA QA presenti | In attesa esito workflow | integration | In esecuzione... |
| 401/403 per endpoint protetti | In attesa esito workflow | integration | In esecuzione... |
<!-- AUTO-QA-END -->

> Esempio di evidenze (le checkbox saranno spuntate dal workflow insieme ai dati riportati sotto):
>
> | Controllo | Storia collegata | Tipo di test (unit/integration/manuale) | Evidenza (link/log, includere header/marker rilevante) |
> | --- | --- | --- | --- |
> | Test con dump disabilitato (marker/header) | ABC-123 | integration | https://example.com/logs/123#marker |
> | Naming export corretto | ABC-123 | unit | https://example.com/logs/456 |
> | CTA QA presenti | ABC-123 | manuale | https://example.com/logs/789 |
> | 401/403 per endpoint protetti | ABC-123 | integration | https://example.com/logs/987 |

## Note aggiuntive
- Dettagli aggiuntivi o rischi noti.
