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

## Secondo giro: oggetti magici (2026-11-02)

Dopo l'import di `tools/import_magic_items_aon.py` (3861 voci OGL nuove) lo
scan `gemma4:e4b` ha segnalato 661 candidati; la revisione ha aggiunto 69
termini (soprattutto artefatti: runelord, signori dei demoni, citta'), piu'
Graydirge trovato rileggendo il campione: 70 nel giro, 178 in tutto. Scartati: divinita' di mitologie
reali (Horus, Anubis, Set, Apep...), folklore (Baba Yaga, Valhalla), nomi
lovecraftiani (Hastur, Leng, Dreamlands); "Sargavan" fuori come "Sargava".

Rischio residuo: nomi minori che ne' il modello ne' la rilettura hanno
colto (es. "Nashina aj-Salihar" in Saliharion). La lista resta aperta.

Esito: 72 voci spostate (A/B), 200 sanitizzate (C); legal_filter 0.

| catalogo | A/B spostate | C sanitizzate |
|---|---|---|
| archetypes | 2 | 1 |
| equipment | 2 | 1 |
| feats | 2 | 1 |
| items | 62 | 187 |
| spells | 4 | 7 |
| talents | 0 | 1 |
| traits | 0 | 2 |

### archetypes (secondo giro)

Spostate (A/B): Dawnflower Dervish; Ustalavic Duelist

Sanitizzate (C): Whirling Dervish

### equipment (secondo giro)

Spostate (A/B): Erutaki coat; Tears of Razmir

Sanitizzate (C): Split-blade sword

### feats (secondo giro)

Spostate (A/B): Pure Legion Assault; Kraggodan's Stance

Sanitizzate (C): Eye of the Arclord

### items (secondo giro)

Spostate (A/B): Belt of Impossible Action (Vudrani); Baldric of Magical Stability (Garundi); Darklands Goggles; Horseshoes of Desert Fury (Keleshite); Lepidstadt Investigator's Hat; Hand of Abendego; Pelt of the Ulfen Wolf; Cloak of Summer and Winter (Triaxian); Brastlewark Brew; Kitharodian Pen; Attentive Mirror; Ointment of Secret Seeing (Ulfen); Medium's Harrow Mat; Saga of the Linnorm Kings; Szuriel's Scabbard; Harrow Deck of Secret Schemes; Droskar's Guiding Ring; Sigil of Kraggodan; Nethysian Ring of Minor Spell Storing; Sihedron Ring; Scepter of the Arclords; Shory Acolyte's Staff; Channeler's Scarf; Shields' Bane (Ulfen); Rostland Edge; Red Crusader's Quill; Talmandor Blade; Crimson Bluff; Iadaran Dress Uniform; Dawnflower Chain Vest; Numerian Resistance Plate; Armor of the Pure Legion; Okeno Madu; Grasp of Droskar; Amatatsu Seal; Decemvirate Helm; Sihedron Tome (Envy); Suishen, Guardian of the Amatatsu; Terendelev's Scales; Throne of Ydersius Ascendant; Thrushmoor Star Stelae; Torc of Kostchtchie; Zellara's Harrow Deck; Alaznist's Hateful Ranseur; Bloodstones of Arazni; Chalice of Lissala; Harrow Deck of Many Things; Lung Bloodstone of Arazni; Mask of the Forgotten Pharaoh; Minderhal's Forge; Mirror of Sorshen; Relic of Kazavon, Armor of Skulls; Relic of Kazavon, Bound Blade; Relic of Kazavon, Crown of Fangs; Relic of Kazavon, Howling Horn; Relic of Kazavon, Shredskin; Relic of Kazavon, Staff of the Slain; Relic of Kazavon, Throne of Nalt; Scepter of Alaznist; Skull of Ydersius; Sorshen's Sinuous Guisarme; Spherical Boat of Zutha

Sanitizzate (C): Belt of the Snake King; Feller's Belt; Ghoulbane Belt; Robe of the Master of Masters; Alabaster Trapping; Pathfinder Greatcoat; Anaphexis Robe; Silent Blade Vest; Summoner Slayer Eyes; Gloves of Personal Purity; Kalistocrat's Gloves; Gauntlets of the Unchained; Mantis Embrace; Veil of Attentiveness; Holy Mask of the Living God; Gray Gambler's Hat; Veil of Veils; Maiden's Helm; Mask of the Mantis; Goz Mask; Dervish Sikke; Helm of the Fanged Crown; Daylight Diadem; Yithian Thought Ring; Falcon Crown; Khepresh of Refuge; Magnate's Miter; Hurricane Crown; Maiden's Promise; Dust of Envy; Gossamer Amberstone; Spidersilk Medallion; Nightstone of Sorrow; Vurra of the Maker; Orb of the Waybringer; Choker of the Queen Bee; Doomsday Key; Slave Collar; Amulet of Radiation Absorption; Deathlurker's Cloak; Great Barghest Hero Cloak; Rimepelt; Golden Eagle Epaulets; Harborwing Cloak; Crow Brother's Cloak; Cloak of the Saga Keeper; Pelt of the Beast; Erinyes Company Cloak; Pelt of Primal Power; Spellsight Bracer; Hex Nail; Riffle Scroll; Caber Twig; Aspis Badge of Last Resort; Kalistocrat's Coin; Bounteous Bath Suffusion; Traveler's Grandiose Carrying Case; Wine of Concordance; Deathgag Elixir; Tablet of Languages Lost; Ki Crystal; Blight Siphoner; Home Stone; Crackling Tassel; Player's Prize; Saliharion; Discretion Charm; Golden Dragon Kite; Figurines of Wondrous Power; Papyrus of Eternal Rest; Chest of Preparedness; Metalseeker Swarm; Seishinru, Spirit Elixir; Gremlin-Skin Drum; Steelbone Frame; Scabbard of the Lost Kiss; Fate-Reader's Lenses; Warden's Cudgel; Jungle Seeker's Monocle; Cavern Compass; Caravan Guardian; Evergreen Seed Pouch; Idol of the Eye; Svingli's Eye; Kikuya's Sensu; Moribund Key; Scabbard of the Efreet; Tyrant's Mark; Relic of a Virtuous Emperor; Beacon of the North; Silent Aviary; Dark Life Ring; Ring of Culturemeld; Ring of Seven Virtues; Utilitarian Rod; Doomsday Staff; Grave Marker Arrow; Everbloom's Rose; Fate Blade; Fiend's Relief; Bloodlight; Perfectionist Shavtoosh; Midsummer Sickle; Buoyant Harpoon; Akitonian Blade; Silverfang; En-Nebi, Blade of the Leopard; Deck of Slivering Fate; Purging Falcata; Talon Sword; Crystalline Starknife; Sadist's Lash; Sword of Tempests; Risen Blade; Slaver's Cane; Daikyu of Commanding Presence; Shard of Winter; Rose Knight's Blade; The Thundering Blade of the House of Sugimatu; Crowcaller; Sword of Vengeance; Talonstrike Sword; Banshee's Howl; Enervating Pistol; Snakebite; Earth Breaker of Righted Injustice; Spiteful Scimitar; Drowscourge; Runeforged; Red Stalker Armor; Painspike Armor; Truefaith Vestments; Stone-eater Armor; Armor of Grim Triumph (Orc); Elven Vengeance; Hide of the Hagfish; Eagle Knight Dress Uniform; Armor of Fragmenting Stone; Suit of Inverted Jade; Panoply of the Fierani Knight (Elf); Tunnel Defender Stoneplate; Blackjacket; Maiden's Panoply; O-Yoroi of Imperial Rule; Maiden's Aegis; Unspeakable One's Vestments; Ring of the Weary Sky; Ukwar; Teralindar's Honor; Argental Font; Deck of Harrowed Tales; Eye of Abenatrex; Funerary Crown of the True King; Mantis Blade; Orrery of Distant Worlds; Pharaoh's Key; Raven's Head; Runeslave Cauldron; Runewell Amulet (Envy); Shinobi Fuhonsen; Soul Lens; The Enthroned King; Void Crystal; Wardstone Shard; Agrimmosh; Anathema Archive; Anima Focus; Blackaxe; Cicatrix; Crook and Flail of Kings; Crown of Fangs; Everdawn Pool; Greatcube of Jayalakshmi; Lamentation of the Faithless; Mog-Lathar, the Petrified Spider; Radiance; Robe of the Rifts; Runewell of Wrath; Sword of Gluttony, Ungarato; Sword of Greed, Chellan; Sword of Lust, Asheia; Sword of Pride, Baraket; Sword of Sloth, Shin-Tari; Sword of Wrath, Garvok; The Gasping Pearl; The Gluttonous Tome; Winter Collector

### spells (secondo giro)

Spostate (A/B): Shield Of The Dawnflower; Shield Of The Dawnflower, Greater; Alaznist's Jinx; Sign of the Dawnflower

Sanitizzate (C): Covetous Aura; Curse Item; Emblem Of Greed; Tears To Wine; Protection From Spores; What Grows Within; Rune Of Rule

### talents (secondo giro)

Spostate (A/B): -

Sanitizzate (C): Swallow Reversal

### traits (secondo giro)

Spostate (A/B): -

Sanitizzate (C): Self-Sustaining; Strength of Submission
