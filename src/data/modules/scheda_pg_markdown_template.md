module_name: "Scheda PG Markdown Template"
version: "1.1"
compatibility:
  core_min: "3.3"
  integrates_with: ["MinMax Builder", "Adventurer Ledger", "Explain Methods", "Ruling Expert", "Hook VTT"]

### 🧙 Scheda Personaggio in Markdown

> **Meta payload (header):**
> ```yaml
> module: scheda_pg_markdown_template.md
> version: "1.1"
> compatibility:
>   core_min: "3.3"
>   integrates_with: ["MinMax Builder", "Adventurer Ledger", "Explain Methods", "Ruling Expert", "Hook VTT"]
> triggers:
>   ledger: "True quando il payload porta valute (pp/gp/sp/cp), ledger_invested_gp o wbl_target_gp: abilita log, audit e KPI."
>   minmax: "True se riempi benchmarks/statistiche_chiave/benchmark_comparison o chiedi QA su DPR/CA/metatier."
>   vtt: "True se map_id, vtt_bundle_path, token_scale_hint o export Foundry/Roll20 sono richiesti."
>   qa: "True per checklist su tabelle popolate, Δ WBL coerente e valute normalizzate (fmt_gp)."
>   explain: "True quando serve allegare regole/procedure didattiche (campi explain.*)."
> operational_policies:
>   ledger_exports: "Limita export a bundle con valuta normalizzata (fmt_gp); annota Δ WBL e cap investimenti; ping Ledger per audit."
>   ledger_limits: "Blocca export se manca la conversione gp o se ledger_invested_gp supera il cap tavolo senza nota master."
>   minmax_reviews: "Coinvolgi MinMax per DPR/Base o CA derivati da archetipi homebrew o benchmark_comparison custom; annota fonti."
>   minmax_blocks: "Se mancano benchmark rilevanti, marca il DPR come ""stub"" e non esportare build finale."
>   vtt_hand-off: "Per mappe/token con licenze sensibili o grid custom, chiedi conferma VTT e evita export automatici."
>   export_limits: "Niente export completo (PDF/JSON) se QA non è passato o se ledger_limits/minmax_blocks sono attivi."
>   explain_scope: "Se explain.* contiene rulings controversi, passa da Ruling Expert prima di pubblicare."
> activation:
>   ledger: "auto (default) ⇒ attiva quando trigger. Usa force_on per includere ledger_invested_gp anche senza valute; force_off per test sandbox."
>   minmax: "auto (default) ⇒ attiva su benchmarks/statistiche_chiave. Usa force_on per review anticipata, force_off per build narrative."
> export_policy:
>   mode: "full|limited|block: usa limited se dati incompleti, block quando export_limits scatta o manca fmt_gp."
>   notes: "CTA breve per il master su cosa sbloccare (es. aggiungi benchmark_comparison o normalizza valute)."
> defaults:
>   show_minmax: true
>   show_vtt: true
>   show_qa: true
>   show_explain: true
>   show_ledger: true
> ```

> **Uso rapido / CTA:**
> - Compila sempre `module`, `version` e `compatibility` nel meta header.
> - Usa `triggers.*` per dichiarare cosa attiva Ledger/MinMax/VTT/QA e `activation.*` per forzare/evitare i flussi auto.
> - Se una policy scatta (ledger_limits/minmax_blocks/export_limits) imposta `export_policy.mode` su `block`/`limited` e scrivi in `export_policy.notes` cosa sbloccare prima di procedere (es. normalizzare `fmt_gp` o aggiungere `benchmark_comparison`).
> - Conferma sempre con il master o con i referenti Ledger/MinMax prima di esportare quando `export_policy.mode` non è `full`.

> **Esempio di payload (stub):**
> ```yaml
> module: scheda_pg_markdown_template.md
> version: "1.1"
> compatibility:
>   core_min: "3.3"
>   integrates_with: ["MinMax Builder", "Adventurer Ledger"]
> triggers:
>   ledger: true   # valuta + Δ WBL ⇒ Ledger
>   minmax: true   # DPR/benchmark richiesti
>   vtt: true      # export Foundry/Roll20
>   qa: true       # QA finale prima dell'export
>   explain: true  # note didattiche per rulings
> activation:
>   ledger: force_on   # includi ledger_invested_gp anche se non hai valute live
>   minmax: auto       # attiva review solo se campi compilati
> operational_policies:
>   ledger_exports: "Annota Δ WBL e cap investimento prima del PDF."
>   ledger_limits: "Blocca export se manca fmt_gp o se cap investimenti non è autorizzato."
>   minmax_reviews: "Richiedi review: archetipi homebrew presenti."
>   minmax_blocks: "Non esportare build finché manca benchmark_comparison."
>   vtt_hand-off: "Serve check licenza token prima di pubblicare."
>   export_limits: "QA bloccante se Δ WBL > +20% o mancano tabelle popolari."
> export_policy:
>   mode: limited   # passa a full solo dopo check QA/Ledger/MinMax
>   notes: "Aggiungi benchmark_comparison + fmt_gp normalizzato per sblocco full."
> print_mode: false
> show_ledger: true
> show_minmax: true
> show_vtt: true
> ```

---

{# ========== SETUP & MACROS ========== #}
{% set PRINT_MODE    = print_mode    | default(false) %}
{% set SHOW_MINMAX   = show_minmax   | default(true)  %}
{% set SHOW_VTT      = show_vtt      | default(true)  %}
{% set SHOW_QA       = show_qa       | default(true)  %}
{% set SHOW_EXPLAIN  = show_explain  | default(true)  %}
{% set SHOW_LEDGER   = show_ledger   | default(true)  %}  {# <-- nuovo: Libro Mastro #}
{% set DECIMAL_COMMA = decimal_comma | default(true)  %}
{% set DESC_FALLBACK = 'n/d' %}

{% macro d(val, fallback='—') -%}
{%- set trimmed = (val|string|trim) -%}
{{ fallback if (val is none or trimmed == '') else (trimmed if (val is string) else val) }}
{%- endmacro %}
{% macro mod(x) -%}{{ (((x|default(10))|int) - 10) // 2 }}{%- endmacro %}
{% macro j(list, sep=', ') -%}{{ (list or []) | select('string') | list | join(sep) }}{%- endmacro %}
{% macro signed(x) -%}{% if x is not none %}{{ "+" if x>=0 else "" }}{{ x }}{% else %}—{% endif %}{%- endmacro %}
{% macro toggle_badge(enabled, label) -%}{{ '🟢' if enabled else '⚪' }} {{ label }}{%- endmacro %}

{# --- Monete / Valorizzazioni (per Adventurer Ledger) --- #}
{% macro to_gp(pp=0,gp=0,sp=0,cp=0) -%}{{ (pp|float)*10 + (gp|float) + (sp|float)/10 + (cp|float)/100 }}{%- endmacro %}
{% macro coin_str(pp=0,gp=0,sp=0,cp=0) -%}
PP {{pp|default(0)}} • GP {{gp|default(0)}} • SP {{sp|default(0)}} • CP {{cp|default(0)}}
{%- endmacro %}
{% macro fmt_gp(x) -%}
{%- set raw = ('{:.2f}'.format(x|float)).rstrip('0').rstrip('.') -%}
{{ (raw.replace('.', ',') if DECIMAL_COMMA else raw) }} gp
{%- endmacro %}

{% set ST  = statistiche or {} %}
{% set STK = statistiche_chiave or {} %}
{% set SAL = salvezze or {} %}
{% set BM  = benchmarks or {} %}
{% set HP  = hp or {} %}
{% set ST_FOR = ST.FOR | default(ST.Forza) | default(ST.forza) | default(10) %}
{% set ST_DES = ST.DES | default(ST.Destrezza) | default(ST.destrezza) | default(10) %}
{% set ST_COS = ST.COS | default(ST.Costituzione) | default(ST.costituzione) | default(10) %}
{% set ST_INT = ST.INT | default(ST.Intelligenza) | default(ST.intelligenza) | default(10) %}
{% set ST_SAG = ST.SAG | default(ST.Saggezza) | default(ST.saggezza) | default(10) %}
{% set ST_CAR = ST.CAR | default(ST.Carisma) | default(ST.carisma) | default(10) %}

{%- set CL = classi or [] -%}
{%- set FIRST_CLASS = (CL[0].nome if CL and CL|length>0 else '—') -%}
{%- set has_alignment = (allineamento | default('') | trim) != '' -%}
{%- set has_deity = (divinita | default('') | trim) != '' -%}
{%- set has_size = (taglia | default('') | trim) != '' -%}
{%- set has_age = (eta | default('') | trim) != '' -%}
{%- set has_sex = (sesso | default('') | trim) != '' -%}
{%- set has_height = (altezza | default('') | trim) != '' -%}
{%- set has_weight = (peso | default('') | trim) != '' -%}
{%- set has_role = (ruolo | default('') | trim) != '' -%}
{%- set has_player_style = (player_style | default('') | trim) != '' -%}
{%- set has_background = (background | default('') | trim) != '' -%}
{%- set has_style_hint = (style_hint(player_style) | default('') | trim) != '' -%}

{% set cur_pp = (currency.pp if currency is defined else pp) | default(0) %}
{% set cur_gp = (currency.gp if currency is defined else gp) | default(0) %}
{% set cur_sp = (currency.sp if currency is defined else sp) | default(0) %}
{% set cur_cp = (currency.cp if currency is defined else cp) | default(0) %}
{% set gp_liquidi = to_gp(cur_pp,cur_gp,cur_sp,cur_cp) %}
{% set gp_investiti = ledger_invested_gp | default(0) %}
{% set gp_totali = gp_liquidi + gp_investiti %}
{% set wbl_target_gp = wbl_target_gp | default(next_wbl_gp | default(0)) %}
{% set wbl_delta_gp = (gp_totali - (wbl_target_gp|float)) %}

{# ----- CA: dodge separato + ricostruzione ----- #}
{% set AC_arm   = AC_arm   | default(0) %}
{% set AC_scudo = AC_scudo | default(0) %}
{% set AC_des   = AC_des   | default(0) %}
{% set AC_defl  = AC_defl  | default(0) %}
{% set AC_nat   = AC_nat   | default(0) %}
{% set AC_dodge = AC_dodge | default(0) %}
{% set AC_misc  = AC_misc  | default(AC_altro | default(0)) %}

{% set AC_tot = AC_tot if (AC_tot is not none)
  else (10 + AC_arm + AC_scudo + AC_des + AC_defl + AC_nat + AC_dodge + AC_misc) %}

{% set CA_touch = 10 + AC_des + AC_defl + AC_dodge + AC_misc %}
{% set CA_ff    = 10 + AC_arm + AC_scudo + AC_defl + AC_nat + AC_misc %}

{# ----- Spell table: robust ----- #}
{% set spell_levels    = spell_levels or [] %}
{% set has_spell_table = (spell_levels|length) > 0 %}

{# Hook Percezione auto se presente skills_map #}
{% set skills_map = skills_map or {} %}
{% if skills_map and skills_map.Percezione and skills_map.Percezione.totale is not none %}
  {% set percezione_tot = skills_map.Percezione.totale %}
{% endif %}

# {{ d(nome, FIRST_CLASS) }} — Liv. {{ get_total_level(CL)|default('—') }} ({{ d(razza, DESC_FALLBACK) }} · {% for c in CL %}{{ c.nome }} ({{ c.livelli }}){% if c.archetipi %} — {{ c.archetipi | join(', ') }}{% endif %}{% if not loop.last %} / {% endif %}{% endfor %})

{% if has_alignment or has_deity -%}
**Allineamento:** {{ d(allineamento, DESC_FALLBACK) }}{% if has_deity %} | **Divinità:** {{ d(divinita, DESC_FALLBACK) }}{% endif %}
{% endif -%}
{% if has_size or has_age or has_sex or has_height or has_weight -%}
**Taglia:** {{ d(taglia, DESC_FALLBACK) }} | **Età:** {{ d(eta, DESC_FALLBACK) }} | **Sesso:** {{ d(sesso, DESC_FALLBACK) }} | **Altezza/Peso:** {{ d(altezza, DESC_FALLBACK) }} / {{ d(peso, DESC_FALLBACK) }}
{% endif -%}
{% if has_role -%}
**Ruolo consigliato:** {{ d(ruolo, DESC_FALLBACK) }}
{% endif -%}
{% if has_player_style or has_style_hint -%}
**Stile interpretativo:** {{ d(player_style, DESC_FALLBACK) }}{% if has_style_hint %} — {{ d(style_hint(player_style), DESC_FALLBACK) }}{% endif %}
{% endif -%}
{% if has_background -%}
**Background breve (5–10 righe):** {{ d(background, DESC_FALLBACK) }}
{% endif %}

{% if not PRINT_MODE %}
---
## Toggle & riepilogo rapido
- {{ toggle_badge(SHOW_MINMAX, 'MINMAX') }} | {{ toggle_badge(SHOW_VTT, 'VTT') }} | {{ toggle_badge(SHOW_QA, 'QA') }} | {{ toggle_badge(SHOW_EXPLAIN, 'EXPLAIN') }} | {{ toggle_badge(SHOW_LEDGER, 'LEDGER') }}
_Policy operative_: attiva **MINMAX** se presenti `statistiche_chiave`/`benchmarks` o richiesto DPR/CA; **LEDGER** quando hai valute, `ledger_invested_gp` o target WBL; **VTT** con `map_id`, bundle o token hint; **QA** per checklist finale/export; **EXPLAIN** se fornisci campi `explain.*` o training rules.
{% if SHOW_MINMAX %}
- **Meta tier / DPR:** {{ d(BM.meta_tier, STK.meta_tier) }} · {{ d(STK.DPR_Base, '—') }}/{{ d(STK.DPR_Nova, '—') }} DPR
- **CA ricostruita:** {{ AC_tot }} (touch {{ CA_touch }}, ff {{ CA_ff }})
{% if ac_breakdown %}
| Fonte | Bonus |
|---|---:|
{% for fonte,bonus in ac_breakdown.items() -%}
| {{ fonte }} | {{ bonus }} |
{% endfor %}
{% endif %}
{% endif %}
{% if SHOW_LEDGER %}
- **Ledger flash:** {{ coin_str(cur_pp,cur_gp,cur_sp,cur_cp) }} ⇒ {{ fmt_gp(gp_liquidi) }} liquidi · Investiti {{ fmt_gp(gp_investiti) }} · Δ WBL {{ signed((wbl_delta_gp)|round(1)) }} gp
{% endif %}
{% if SHOW_VTT %}
- **VTT hook:** Map {{ d(map_id) }} · Token {{ d(token_scale_hint, 'M') }} · Grid {{ d(recommended_grid_size) }}
{% endif %}
{% if SHOW_QA %}
- **QA ready:** valuta tabelle popolate e coerenza valute ({{ coin_str(pp, gp, sp, cp) }})
{% endif %}
{% if SHOW_EXPLAIN %}
- **Explain (tldr):** {{ d(explain.tldr, 'aggiungi regola o procedura chiave') }}
{% endif %}
{% endif %}

---

## Statistiche fondamentali
- **For** {{ ST_FOR }} (mod {{ mod(ST_FOR) }})
- **Des** {{ ST_DES }} (mod {{ mod(ST_DES) }})
- **Cos** {{ ST_COS }} (mod {{ mod(ST_COS) }})
- **Int** {{ ST_INT }} (mod {{ mod(ST_INT) }})
- **Sag** {{ ST_SAG }} (mod {{ mod(ST_SAG) }})
- **Car** {{ ST_CAR }} (mod {{ mod(ST_CAR) }})

- **PF (HP):** {{ d(STK.PF) }} | **CA:** {{ d(STK.CA, AC_tot) }}  
- **CA (breakdown):** {{ AC_tot }} = 10 + Arm {{ AC_arm }} + Scudo {{ AC_scudo }} + Des {{ AC_des }} + Defl {{ AC_defl }} + Nat {{ AC_nat }} + Dodge {{ AC_dodge }} + Altro {{ AC_misc }}  
- **CA Var.:** Contatto {{ CA_touch }} · Colto alla sprovvista {{ CA_ff }}  
- **Tiri Salvezza:** Temp {{ d(SAL.Tempra) }} / Riflessi {{ d(SAL.Riflessi) }} / Volontà {{ d(SAL.Volontà) }}  
- **BAB:** {{ d(BAB) }} | **Iniziativa:** {{ d(init) }} | **Velocità:** {{ d(speed) }}
- **CMB/CMD:** {{ d(CMB) }} / {{ d(CMD) }}

{% set CMD_base = 10 + (BAB|default(0)) + (mod(ST_FOR) if use_str_for_cmd|default(true) else mod(ST_DES)) + mod(ST_DES) + size_mod_cmd|default(0) + cmd_altro|default(0) %}
- **CMD (dettaglio):** {{ CMD|default(CMD_base) }} = 10 + BAB {{ BAB|default(0) }} + For/Des {{ (mod(ST_FOR) if use_str_for_cmd|default(true) else mod(ST_DES)) }} + Des {{ mod(ST_DES) }} + Taglia {{ size_mod_cmd|default(0) }} + Altro {{ cmd_altro|default(0) }}

- **PE (XP):** {{ d(xp_correnti) }} / {{ d(xp_prossimo_livello) }}

---

{% if SHOW_MINMAX %}
## Breakdown avanzato (PF/CA)
- **PF totali:** {{ d(pf_totali, STK.PF) }} | **PF per livello:** {{ d(pf_per_livello) }}
{% if HP %}
| Fonte PF | Valore |
|---|---:|
{% for k,v in HP.items() -%}
| {{ k }} | {{ v }} |
{% endfor %}
{% endif %}
{% if ac_breakdown %}
| Fonte CA | Bonus |
|---|---:|
{% for fonte,bonus in ac_breakdown.items() -%}
| {{ fonte }} | {{ bonus }} |
{% endfor %}
{% else %}
_Nessun breakdown CA dettagliato nel payload._
{% endif %}
{% endif %}

---

## Difese Speciali
- **RD/Res/Imm:** {{ d(rd_res_imm) }}  
- **RS:** {{ d(rs) }} | **Guarigione rapida/Rigenerazione:** {{ d(heal_regen) }}  
- **Sensi:** {{ d(sensi) }} | **Percezione (tot):** {{ d(percezione_tot) }}

---

## Combattimento
### Armi e attacchi
| Arma | Tipo | Attacco | Danni | Critico | Portata | Note |
|---|---|---:|---|---|---|---|
{% for a in (armi or []) -%}
| {{ d(a.nome) }} | {{ d(a.tipo) }} | {{ d(a.attacco) }} | {{ d(a.danni) }} | {{ d(a.critico) }} | {{ d(a.portata) }} | {{ a.note | default('') }} |
{%- endfor %}
{% if (armi or [])|length == 0 %}_(Nessuna arma strutturata: derivabile da `equipaggiamento` o aggiungerla qui.)_{% endif %}

- **Attacchi naturali:** {{ d(attacchi_naturali) }}  
- **Capacità speciali:** {{ d(capitolo_capacita, capacita_speciali) }}

### Manovre CMB
| Manovra | Bonus |
|---|---:|
| Disarm | {{ d(cmb_disarm) }} |
| Trip   | {{ d(cmb_trip) }} |
| Grapple| {{ d(cmb_grapple) }} |
| Bull Rush | {{ d(cmb_bull_rush) }} |
| Sunder | {{ d(cmb_sunder) }} |

---

## Economia d’Azione
- **AoO/round:** {{ d(aoo_per_round) }}  
- **Swift usata?:** {{ d(swift_used,'no') }}  
- **Immediate pronte?:** {{ d(immediate_ready,'sì') }}

---

## Armatura (tecnica)
- **ACP:** {{ d(acp) }} | **Max Des:** {{ d(max_dex) }} | **ASF:** {{ d(asf_pct) }}% | **Velocità ridotta:** {{ d(speed_armor_penalty) }}

---

## Abilità (Skills)
| Abilità | Gradi | Mod Car | Var | Classe? | Totale |
|---|---:|---:|---:|:--:|---:|
{% for s in (skills or []) %}
| {{ d(s.nome) }} | {{ s.gradi|default(0) }} | {{ signed(s.mod_car|default(0)) }} | {{ signed(s.var|default(0)) }} | {{ '✓' if s.classe else '' }} | {{ s.totale|default(s.gradi|default(0) + s.mod_car|default(0) + s.var|default(0) + (3 if s.classe else 0)) }} |
{% else %}
_Nessuna abilità strutturata._
{% endfor %}

---

## Talenti, Tratti & Difetti
- **Talenti:** {% set feats = (progressione or []) | map(attribute='talento') | select('string') | reject('equalto', None) | list %}{{ j(feats) or '—' }}
- **Tratti:** {% if tratti %}{% for t in tratti %}{{ d(t.nome) }}{{ ', ' if not loop.last }}{% endfor %}{% else %}—{% endif %}
- **Difetti:** {{ d(difetti) }}

---

## Poteri di Classe / Archetipi
{{ d(poteri_classe) }}

**Usi/giorno chiave:** {{ d(usi_giorno_chiave) }}

---

## Incantesimi / Capacità Magiche
- **Classe da incantatore:** {{ d(classe_incantatore, FIRST_CLASS) }}
- **CD base incantesimi:** {{ d(spell_dc_base) }} | **LI:** {{ d(livello_incantatore) }}

**Conosciuti/Preparati**
{% for lvl in (magia or {}).keys() | map('int') | list | sort %}
- **{{ lvl }}°:** {{ (magia[lvl] or []) | join(', ') }}
{% endfor %}
{% if (magia or {})|length == 0 %}_Nessun incantesimo conosciuto o preparato specificato._{% endif %}

{% if has_spell_table %}
| Liv | Slot/giorno | Preparati | Conosciuti | CD |
|---:|---:|---:|---:|---:|
{% for sl in spell_levels -%}
| {{ sl.liv }} | {{ d(sl.per_day) }} | {{ d(sl.prepared) }} | {{ d(sl.known) }} | {{ d(sl.dc) }} |
{%- endfor %}
{% elif slot_incantesimi %}
- **Slot per giorno:** {{ d(slot_incantesimi) }}
{% else %}
_Nessuna tabella incantesimi disponibile._
{% endif %}

### Incantatore (tecnico)
{% if concentration_bonus is not none %}
- **Concentrazione:** {{ concentration_bonus }}
{% else %}
- **Concentrazione (hint):** LI {{ d(livello_incantatore,0) }} + mod stat chiave + vari
{% endif %}
- **Penetrazione Magica:** {{ d(spell_penetration_bonus) }}  
- **CD per Scuola:** {{ d(dc_per_school) }}

---

## Routine di Round (rapida)
1) **Buff chiave:** {{ d(buffs_open) }}  
2) **Posizionamento:** {{ d(movement_plan) }}  
3) **Output:** {{ d(attack_plan) }}  
**Priorità reattive:** {{ d(reactions_list, 'Step laterale; AoO; Immediate') }}

---

## Risorse Giornaliere
| Risorsa | Max | Usate | Rimaste | Reset |
|---|---:|---:|---:|---|
{% set risorse = risorse_giornaliere or [] %}
{% if risorse %}
{% for r in risorse -%}
| {{ d(r.nome) }} | {{ d(r.max) }} | {{ d(r.usate,0) }} | {{ (r.max|default(0)) - (r.usate|default(0)) }} | {{ d(r.reset,'giornaliero') }} |
{%- endfor %}
{% else %}
| Rage / Ki / Panache / Grit / Arcane Pool / Performance | {{ d(res_max) }} | {{ d(res_used,0) }} | {{ (res_max|default(0)) - (res_used|default(0)) }} | {{ d(res_reset,'giornaliero') }} |
{% endif %}

---

## Consumabili
- **Pozioni:** {{ d(consum_potions) }}  
- **Pergamene:** {{ d(consum_scrolls) }}  
- **Bacchette (cariche):** {{ d(consum_wands) }}

---

## WBL & Shopping
- **Budget attuale:** {{ gp|default(0) }} gp | **Breakpoint prossimo:** {{ d(next_wbl_gp) }} gp
- **Priorità acquisti:** {{ d(buylist_priority) }}

---

## Equipaggiamento
- {{ (equipaggiamento or []) | join(', ') if equipaggiamento else '—' }}
- **Armi/Armature/Oggetti:** {{ d(equip_base) }}  
- **Peso totale trasportato:** {{ d(peso_totale) }}  
- **Capacità di trasporto:** L {{ d(carico_leggero) }} / M {{ d(carico_medio) }} / P {{ d(carico_pesante) }}  
- **Valute:** Rame {{ cp|default(0) }} • Argento {{ sp|default(0) }} • Oro {{ gp|default(0) }} • Platino {{ pp|default(0) }}

---

## Lingue & Varie
- **Lingue:** {{ (lingue or []) | join(', ') if lingue else '—' }}  
- **Punti Eroe (opz.):** {{ d(hero_points) }}  
- **Altre note:** {{ d(note_varie) }}

---

## Companion / Famigli
{{ d(companion) }}

---

## Psicologia & Roleplay
- **Sinergie**: {{ j(sinergie, ', ') or d(roleplay_sinergie) }}
- **Teoria dominante**: {{ d(teoria_dominante, 'Jung/OCEAN/Enneagramma') }}
- **Comportamento prevalente**: {{ d(comportamento_prevalente, 'es. introverso, impulsivo, empatico') }}
- **Stile decisionale**: {{ d(stile_decisionale, 'es. segue l’istinto, valuta i rischi, ecc.') }}
- **Motto/Frase tipica/Modi di dire/Accento**: {{ d(motto_o_frase, 'es. accento locale, intercalare ricorrente') }}
- **Spunti per interpretazione**: {{ d(spunti_interpretativi, 'es. parla per enigmi, ama raccontare storie') }}
- **Background Narrativo**: {{ d(background_narrativo, 'breve backstory coerente con razza, classe e tratti') }}

---

{# ========== LIBRO MASTRO DELL’AVVENTURIERO (LEDGER) ========== #}
{% if SHOW_LEDGER %}
## 💰 Adventurer Ledger — KPI & Movimenti
- **Cassa (liquidi):** {{ coin_str(cur_pp,cur_gp,cur_sp,cur_cp) }} = **{{ fmt_gp(gp_liquidi) }}**
- **Valore investito (gear):** **{{ fmt_gp(gp_investiti) }}** · **Wealth totale:** **{{ fmt_gp(gp_totali) }}**
- **WBL target (liv {{ get_total_level(CL)|default(1) }}):** {{ fmt_gp(wbl_target_gp) }} · **Δ vs WBL:** {{ signed((wbl_delta_gp)|round(1)) }} gp
- **Encumbrance hint:** {{ d(ledger_encumbrance_hint, 'ok') }}

### Movimenti (ultimi / sessione)
| Data | Tipo | Oggetto/Voce | Q.tà | Val. unit | Totale | Δ GP | Fonte (AP/SX) | PFS |
|---|---|---|---:|---:|---:|---:|---|:--:|
{% for m in (ledger_movimenti or []) -%}
| {{ d(m.data) }} | {{ d(m.tipo) }} | {{ d(m.oggetto) }} | {{ d(m.qty,1) }} | {{ d(m.vu) }} | {{ d(m.tot) }} | {{ d(m.delta_gp) }} | {{ d(m.source) }} | {{ '✓' if m.pfs else '' }} |
{%- endfor %}
{% if (ledger_movimenti or [])|length == 0 %}_Nessun movimento registrato._{% endif %}

### Loot Parcels (non ancora liquidati)
| Parcella | Stima gp | Assegnatario | Note |
|---|---:|---|---|
{% for p in (ledger_parcels or []) -%}
| {{ d(p.nome) }} | {{ d(p.val_gp) }} | {{ d(p.assegnatario) }} | {{ d(p.note) }} |
{%- endfor %}
{% if (ledger_parcels or [])|length == 0 %}_Nessun loot in attesa._{% endif %}

### Coda Crafting
| Item | DC | Giorni | Costo materie | Risparmio | Stato |
|---|---:|---:|---:|---:|---|
{% for c in (ledger_crafting or []) -%}
| {{ d(c.item) }} | {{ d(c.dc) }} | {{ d(c.days) }} | {{ d(c.cost) }} | {{ d(c.saving) }} | {{ d(c.status,'open') }} |
{%- endfor %}
{% if (ledger_crafting or [])|length == 0 %}_Nessun crafting pianificato._{% endif %}

### Audit & PFS
- **Flag non PFS-legal:** {{ d(ledger_pfs_flags, '—') }}
- **Note GM/Audit:** {{ d(ledger_audit_notes, '—') }}

{% endif %}

{% if not PRINT_MODE and SHOW_VTT %}
---
## Hook VTT / Export
- **Map ID:** {{ d(map_id) }} | **Bundle asset:** {{ d(vtt_bundle_path) }}
- **Preset luci:** {{ d(vtt_light, 'day') }} | **Token scale:** {{ d(token_scale_hint, 'M') }}
- **Grid consigliata:** {{ d(recommended_grid_size) }} | **Safe/Bleed:** {{ d(safe_area_pct, 5) }}% / {{ d(bleed_pct, 2) }}%
- **Note GM:** {{ d(vtt_gm_notes) }}  <!-- 2–3 POI, percorsi, consigli Foundry/Roll20 -->
- **Formati supportati:** Markdown strutturato, JSON ledger/vtt_json, blocchi compatibili con VTT.
- **Note localizzazione numerica:** separatore {{ ',' if DECIMAL_COMMA else '.' }}, unità in gp.
- **CTA export:** /export_pg_sheet • /export_pg_sheet_json (payload meta richiesto: `version`, `compatibility.core_min`, `compatibility.integrates_with`)
{% endif %}

---

{# ========== SEZIONE DIDATTICA INTEGRATA (EXPLAIN) ========== #}
{% if not PRINT_MODE and SHOW_EXPLAIN %}
---
## Explain – Regola & Procedura (multi‑metodo)
- **Regola (in una riga):** {{ d(explain.tldr) }}
- **Contesto & Scopo:** {{ d(explain.context) }}

### Procedura passo‑passo
{{ d(explain.step_by_step) }}

### Metodo 2 – Algoritmico / Flow
{{ d(explain.algorithmic) }}

### Metodo 3 – Analogia / Metafora
{{ d(explain.analogy) }}

### Errori comuni (e come evitarli)
{{ d(explain.common_mistakes) }}

### RAW vs RAI (edge cases)
{{ d(explain.raw_vs_rai) }}

### Esempio numerico rapido
{{ d(explain.numeric_example) }}

### Verifica / Quiz lampo (3 domande)
{{ d(explain.quick_quiz) }}

### Checklist di applicazione al tavolo
- {{ d(explain.checklist) }}

### Fonti didattiche (puntuali)
- {{ d(explain.sources) }}  {# es. AoN → CRB p.X; FAQ Paizo (link), blog dev #}
{% endif %}

{# ========== TECNICO/ANALISI (toggle) ========== #}
{% if not PRINT_MODE and SHOW_MINMAX %}
---
## Analisi MinMax
- **DPR medio (base/nova):** {{ d(STK.DPR_Base) }} / {{ d(STK.DPR_Nova) }}
- **Sostenibilità difensiva:** {{ d(BM.Defense_status) }} {{ (BM.Defense_delta ~ '%') if BM.Defense_delta is not none else '' }}
- **Meta Tier:** {{ d(BM.meta_tier, STK.meta_tier) }}

**Benchmark (auto) — Ref: {{ d(benchmark_reference_label, FIRST_CLASS) }}**
| Parametro | Stato | Δ vs Ref |
|---|---:|---:|
| DPR 1–3 | {{ d(BM.DPR_early_status) }} | {{ BM.DPR_early_delta if BM.DPR_early_delta is not none else '—' }}% |
| DPR 4+  | {{ d(BM.DPR_late_status)  }} | {{ BM.DPR_late_delta  if BM.DPR_late_delta  is not none else '—' }}% |
| Difesa  | {{ d(BM.Defense_status)   }} | {{ BM.Defense_delta   if BM.Defense_delta   is not none else '—' }}% |
| Buff    | {{ d(BM.Buff_status) }} | – |
| Azioni  | {{ d(BM.Actions_status) }} | – |
| Scaling | {{ d(BM.Scaling_status) }} | – |

🔥 **Risk Heatmap (≥2):** Feat → {{ j(BM.risk_top3.feats) }} · Spell → {{ j(BM.risk_top3.spells) }}  
🏷 **Origine suggerimenti:** {{ source_mix_summary() }}
{% if benchmark_comparison %}
---
## Benchmark Comparativo
**Riferimento:** {{ benchmark_comparison.reference_label }} ({{ 'Auto' if benchmark_comparison.auto else 'Manuale' }}){% if benchmark_comparison.timestamp %} — {{ benchmark_comparison.timestamp }}{% endif %}
| Categoria | Stato | Δ % |
|---|---|---:|
{% for k,v in benchmark_comparison.comparison.items() -%}
| {{ k }} | {{ v.status }} | {{ v.diff }} |
{%- endfor %}
{% endif %}

{% endif %}

{% if not PRINT_MODE and SHOW_QA %}
---
## QA rapido
- **Tabelle popolate?:** armi/skill/incantesimi non vuote o placeholder indicato.
- **Valute normalizzate:** {{ coin_str(pp, gp, sp, cp) }} (usa fmt_gp per export).
- **Coerenza WBL:** Δ vs target {{ d(wbl_delta_gp) }} gp; vendite/acquisti loggati nel ledger.
- **Badge/Lingua:** tag PFS/RAW se noti; lingua coerente con prompt.
{% endif %}

---
## Output checklist (inserire nel render finale)
- Header con toggle attivi (MINMAX/VTT/QA/EXPLAIN/LEDGER) e lingua.
- Fonti/tag: RAW/PFS/HR/META e richiami al Ledger/Explain/MinMax usati.
- Struttura minima: sommario PG, blocchi statistici, economia (ledger/WBL), eventuale sezione Explain/MinMax.
- Dati numerici formattati con {{ ',' if DECIMAL_COMMA else '.' }} come separatore decimale e unità gp/%.
- Sezioni vuote: sostituire con placeholder espliciti per evitare header orfani.

{% if not PRINT_MODE %}
---
## Suggerimenti interpretativi
- {{ d(spunti_interpretativi) }}
{% endif %}

---
{# BEGIN SOURCE_GOVERNANCE_V1 #}
{# META breadcrumb: mostra solo se esistono fonti META; RAW check dinamico (✔/⏳) #}
{% set ns = namespace(has_meta=false, has_raw=false) %}

{# 1) Detect META sources (preferisci 'level' META_*) + detect RAW anchors in meta links #}
{% for f in (fonti_meta or []) %}
  {% if f.level and f.level.startswith('META_') %}
    {% set ns.has_meta = true %}
  {% elif f.tipo and f.tipo.startswith('META') %}
    {% set ns.has_meta = true %}
  {% endif %}

  {% if f.link and ('aonprd.com' in (f.link|lower) or 'paizo.com' in (f.link|lower) or 'archivesofnethys' in (f.link|lower)) %}
    {% set ns.has_raw = true %}
  {% endif %}
{% endfor %}

{# 2) Detect RAW anchors in 'fonti' (stringhe o dict) #}
{% for f in (fonti or []) %}
  {% if f is string and ('aonprd.com' in (f|lower) or 'paizo.com' in (f|lower) or 'archivesofnethys' in (f|lower)) %}
    {% set ns.has_raw = true %}
  {% elif f is mapping %}
    {% set _u = f.url or f.link or f.source_url %}
    {% if _u and ('aonprd.com' in (_u|lower) or 'paizo.com' in (_u|lower) or 'archivesofnethys' in (_u|lower)) %}
      {% set ns.has_raw = true %}
    {% endif %}
  {% endif %}
{% endfor %}

{% if ns.has_meta %}
> 🔍 META-SEARCH → 📖 RAW check {{ '✔' if ns.has_raw else '⏳' }} → 🧠 META-ANALYSIS → VERDETTO
{% endif %}
{# END SOURCE_GOVERNANCE_V1 #}
> 📎 Fonti Meta (badge sintetico): {{ lookup_meta_badges('any') or '—' }}

---
## Profilo ruolistico (“alla Locanda”)
- **Modello psicologico:** {{ d(modello_psico) }} (es. Jung/OCEAN/Enneagramma)  
- **Stile decisionale:** {{ d(stile_decisionale) }}  
- **Storia personale (perché in avventura):** {{ d(storia_personale) }}  
- **Relazioni & legami:** {{ d(relazioni_legami) }} *(un PNG caro, una rivalità, un giuramento)*  
- **Ganci di campagna:** {{ d(ganci_campagna) }} *(per restare nel party)*  
- **Flavor RP:** {{ d(flavor_rp) }} *(tic, frasi tipiche, feticci/ricordi)*

---
## Canone & Fonti
- **Edizione di riferimento:** PF1e  
- **Fonti primarie (📗):** {{ d(fonti_primarie) }}  
- **Secondarie (🔎):** {{ d(fonti_secondarie) }}  
- **Varianti PFS-Lore (🧭):** {{ d(pfs_varianti) }}  
- **Dev Insight (🧪):** {{ d(dev_insight) }}  
- **House Lore (❗):** {{ d(house_lore_note) }}  
- **Citazioni brevi (≤25 parole):**
{% for c in (citazioni_brevi or []) -%}
- “{{ c.estratto }}” — {{ c.fonte }}{{ ' ' ~ c.pagina_opz if c.pagina_opz else '' }}
{%- endfor %}

---
## Collegamenti di Campagna
- **SX00 (dashboard):** {{ d(sx00_link) }}
- **AV corrente:** {{ d(av_code) }} | **SX correlate:** {{ d(sx_codes) }}
- **Fazioni (NC) collegate:** {{ d(fazioni_collegate) }}
- **Thread aperti / milestone:** {{ d(thread_aperti) }}
{% if not PRINT_MODE and SHOW_QA %}
---
## QA & Spoiler
- **spoiler_mode:** {{ d(spoiler_mode, 'light') }}  
- **AP warning:** {{ d(ap_warning) }}  
- **Confidence:** {{ d(confidence_score) }} | **Uncertainty flags:** {{ d(uncertainty_flags) }}

{% if glossario_golarion %}
---
## Glossario Golarion (rapido)
{% for g in glossario_golarion.termini or [] -%}
- **{{ g.termine }}**: {{ g.def }}
{%- endfor %}
{% endif %}

---
## Canone & Fonti META
- **Fonti (RAW/PFS se presenti):** {{ (fonti or []) | join(', ') if fonti else '—' }}
- **Fonti META (ord. autorità):** {% for f in (fonti_meta or []) %}{{ f.badge }} [{{ f.tipo }}]({{ f.link }}){% if not loop.last %} · {% endif %}{% endfor %}

---
## Regole & QA
- **Regole attive:** {{ rules_status_text() }}  
- **QA export gate:** Core={{ 'OK' if validate_core_ok else '—' }}, Feats={{ 'OK' if validate_feats_ok else '—' }}, Sim={{ 'OK' if simulate_ok else '—' }}
{% endif %}

