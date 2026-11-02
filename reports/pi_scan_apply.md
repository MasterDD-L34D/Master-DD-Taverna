# Scan PI con modello locale -- applicazione policy A/B/C (2026-11-02)

Strumento: `tools/apply_pi_scan_policy.py --write`. Termini nuovi del gate:
`GATE_LLM_SCAN_TERMS` in `tools/legal_filter.py` (108 termini),
sostituzioni description-only in `tools/sanitize_reference_pi.py`.

## Metodo

- Il modello locale (Ollama `gemma4:e4b`, prompt v2) ha SEGNALATO candidati su
  7742 voci feats/archetypes/spells; la lista del gate e' la revisione a mano.
- Prova ripetuta prima dello scan: 40 voci a risposta nota, 3 giri per modello.
  gemma4:e4b 17-18/21 PI note e 0 falsi positivi su 19; qwen3.5:9b 16-18/21 ma
  1-4 falsi positivi. Il modello serve per i nomi che la lista non conosce:
  i suoi errori residui erano tutti su termini gia' in lista.
- Scartati in revisione: creature e razze dei bestiari OGL, cosmologia (Abyss,
  Axis, First World...), e i termini gia' esclusi per decisione documentata
  (Sargava, Shackles, Linnorm da solo).
- Titoli di manuale (`BOOK_TITLES`: Dragon Empires Primer, Heroes of the
  Darklands, Harrow Handbook) mascherati: policy titoli libro separata.

## Policy (come 2026-07-19)

- **A** PI nel nome e **B** PI nei prerequisiti: spostamento verbatim in
  `pi_local_only/<kind>_local.json`, in AGGIUNTA alle voci delle policy
  precedenti (mai sovrascritte).
- **C** PI solo nel testo: sanitize in place (description-only); i tag
  identificativi (`race:triaxian`) si tolgono.
- Riferimenti pendenti: 0 (una voce che cita una spostata nei prerequisiti
  contiene il suo nome, quindi e' B anch'essa).
- Limite noto: una sostituzione a inizio frase resta minuscola (stesso
  comportamento delle sostituzioni precedenti).
- Il manifest conta i file locali reali del checkout principale: lanciato in
  un worktree senza `pi_local_only`, lo strumento conterebbe solo le voci
  nuove. Va lanciato dove i file locali ci sono.

## Esito: 110 voci spostate (A/B), 152 sanitizzate (C)

| catalogo | A/B spostate | C sanitizzate |
|---|---|---|
| archetypes | 39 | 56 |
| equipment | 1 | 3 |
| feats | 48 | 27 |
| races | 1 | 0 |
| spells | 10 | 46 |
| talents | 4 | 8 |
| traits | 7 | 12 |

### archetypes

Spostate (A/B): Numerian Liberator; Pitax: Academy of Grand Arts; Speaker of the Palatine Eye; Voice of Brigh; Mendevian Priest; Green Faith Initiate; Molthuni Defender; Harrow Warden; Iroran Paladin; Scion of Talmandor; Abendego Diver; Darklands Sailor; Nirmathi Irregular; Tanglebriar Demonslayer; Bekyar Kidnapper; Galtan Agitator; Kintargo Rebel; Numerian Scavenger; Okeno Liberator; Sczarni Swindler; Razmiran Priest; Jistkan Artificer; Harrowed Society Student; Magaambyan Initiate; Ulfen Beast-Wrestler; Green Faith Marshal; Lepidstadt Inspector; Cinderlands Adept; Nexian Channeler; Rivethun Spirit Channeler; Hag of Gyronna; Nexian Spellspy; Keleshite Prophet; Bekyar Demon Dancer; Rostland Bravo; Jistkan Magistrate; Molthuni Arsenal Chaplain; Magaambyan Telepath; Sczarni Executioner

Sanitizzate (C): Geminate Invoker; Savage Technologist; Argent Voice; Lotus Geisha; Halcyon Druid; Season Keeper; Tempest Druid; Ustalavic Duelist; Silver Champion; Galvanic Saboteur; Ilsurian Archer; Raven Master; Eldritch Scoundrel; Guerrilla; Stone Warder; Umbral Scion; Shadowcaster; Card Caster; Magic Warrior; Sigilus; Aerochemist; Blightseeker; Gloom Chymist; Aeromancer; Enlightened Bloodrager; Symbol Striker; Knight of Arnisant; Qabarat Outrider; Sister-in-Arms; Vermin Tamer; Scatter Gunner; Uprooter Scout; Keeper of Construct; Suit Seeker; Blightburner; Ashiftah; Cartomancer; Demon-Sworn; Black-Blooded Oracle; Story Summoner; Overseer; True Silvered Throne; Augur; Dragon Skald; Wyrm Singer; Mantis Zealot; Sixth Wing Bulwark; Chart Caster; Esoteric Initiate; Terror Weaver; Involutionist; Yojimbo; Seal-Breaker; Darklantern; Imperial Agent; Teisatsu

### equipment

Spostate (A/B): Gray maiden plate

Sanitizzate (C): Spirit offerings; Vault altimeter; Whale oil

### feats

Spostate (A/B): Green Faith Acolyte; Shade of the Uskwood; Talmandor's Lifting; Calm Disposition; Disassemble Magic Item; Fearsome Barricade; Grand Master Performer; Master Performer; Silent Performer; Verbose Performer; Whispered Knowledge; Beacon Of Hope; Believable Veils; Bloody Sabres; Channel Hate; Divine Barrier; Hunter Of Dahak; Intrepid Rescuer; Siphon Channel; Troth Of The Forgotten Pharaoh; Strongarm; Alien Mindpaths; Diplomatic Ruse; High Magic Focus; One Mind; Pursuit Of Glory; Startoss Comet; Startoss Shower; Startoss Style; Red Mantis Collaborator; Whispering Way Disciple; Thrune Trusted Agent; Golden League Tattoos; Favor Of The Empress Of Torrents; Touch Of The Brackish Emperor; Expert Boarder; Falcon's Cry; Legionnaire's Inspiration; Twilight Tattoo; Gray Maiden Initiate; Extra Spontaneous Spell Mastery; Acadamae Graduate; Berserker's Cry; Client; Dark Affinity; Golden Legion's Stayed Blade; Knight of the Twisted Word; Swamp Dweller

Sanitizzate (C): Arcane Vendetta; Fortune Teller; Harrowed; Wand Dancer; Eagle Knight Candidate; Touched By Sacred Fire; Tapestry Traveler; Harrowed Summoning; Deadly Dealer; Gruesome Butcher; Black Marketeer; Supernatural Spy; Aspis Partner; Cypher Magic; Cypher Script; Agile Maiden; Sisterhood Dedication; Sisterhood Rampart; Sisterhood Style; Unbreakable; Scholar; Blade Of The Purge; Eyes Of The Purge; Fiendish Wings; Partner; Shrewd Liason; Storm Breaker

### races

Spostate (A/B): Triaxian

Sanitizzate (C): -

### spells

Spostate (A/B): Aram Zey's Focus; Aram Zey's Trap Ward; Irriseni Mirror Sight; Jatembe's Ire; Apsu's Shining Scales; Dahak's Release; Sarzari Shadow Memory; Ablative Sphere (Garundi); Burning Arc (Keleshite); Snow Shape (Ulfen)

Sanitizzate (C): Arcane Reinforcement; Canopic Conversion; Chastise; Summon Elemental Steed; Hibernate; Sotto Voce; Tomb Legion; Tripvine; Harrowing; Teleport Trap; Ablative Sphere; Snow Shape; Gilded Whispers; Stolen Light; Call Weapon; Crusader's Edge; Eaglesoul; Eldritch Conduit; Geniekind; Martyr's Bargain; Music of the Spheres; Suppress Primal Magic; Zone of Foul Flames; Summon Greater Demon; Speak Local Language; Garrulous Grin; Passing Fancy; Draconic Ally; Frigid Souls; Scarify; Spirit Share; Tactical Adaptation; Hidden Knowledge; Rune Of Rule; Brightest Light; Preserve Grace; Planar Inquiry; Bone Flense; Mirror Mantis; Bloodstone Mirror; Eroding Ray; Fastidiousness; Hallucinatory Decor; Litany of the Red Crusader; Unflappable Mien; Unspoken Name

### talents

Spostate (A/B): Kelizandri’s Tide; Sczarni Smuggler; Harrow Strike; Harrow

Sanitizzate (C): Papercraft Tools; The Whole Time; Harrowing Curse; Kalistocrat's Acumen; Shackle Smash; Rakshasa's Fortune; Order of Vengeance; Order of the Green

### traits

Spostate (A/B): Witty Repartee; Soul-Searcher's Strength; Rivethun Adherent; Darklands Scholar; Darklands Trader; Jistkan Scholar; Savant

Sanitizzate (C): Permanent Scars; Deep Faith; Imperfect Recall; Kalistocratic Prophecy; Light in the Darkness; Scourge of the Darkness; Self-Sustaining; Black Blood Heritage; Mechanical Aptitude; Secret Scrolls; Excellent Penmanship; Student of Philosophy
