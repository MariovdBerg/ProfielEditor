# Profieleditor

Interactieve editor in de browser voor Hydra-NL/HydraRing-profielen (`.prfl`). Je bladert door de dijkvakken van
een traject, past per vak het profiel aan in een grafiek en slaat het aangepaste profiel op. Elke wijziging wordt
direct gecontroleerd met [prflcheck](https://github.com/MariovdBerg/ProfielCheckPython).

```
prfl-map (.prfl) ───┬─> 1. inlezen en koppelen     dijkvakken per traject, met prflcheck-status
koppeltabel (.xlsx) ┤   2. aangepaste versies      gezocht in de uitvoermap
AHN-shapefile ──────┘   3. bewerken in de grafiek  punten, voorland, dam; AHN-lijnen op de achtergrond
                        4. opslaan                 uitvoer_map/<naam>_aangepast.prfl (versie 3 of 4)
```

De editor bestaat uit een kleine lokale Python-webserver (`src\app.py`, alleen de standaardbibliotheek) en een
HTML/JavaScript-pagina (`src\static\`). De enige afhankelijkheid is prflcheck.

**Auteurs:** Dion Rovers, Ilian de Snoo, Mario van den Berg, Claude  
**Copyright:** © 2026 HKV lijn in water B.V.  
**Licentie:** [EUPL-1.2](LICENSE)

## Inhoud

- [Snel starten (testdata)](#snel-starten-testdata)
- [Installatie](#installatie)
- [Instellingen](#instellingen): [ini-bestand](#het-ini-bestand), [opdrachtregel](#opdrachtregel)
- [Invoer](#invoer): [profielen](#profielen), [koppeltabel](#koppeltabel), [aangepaste versies](#aangepaste-versies), [AHN-shapefile](#ahn-shapefile)
- [Gebruik](#gebruik): [lijst](#lijst-met-dijkvakken), [grafiek](#grafiek), [opslaan](#opslaan), [sneltoetsen](#sneltoetsen)
- [Uitvoer](#uitvoer)
- Verder: [ontwikkelen en testen](#ontwikkelen-en-testen), [licentie](#licentie)

## Snel starten (testdata)

Er komt testdata mee in `tests\`: elf profielen uit de trajecten 34-1, 34a-1 en 35-2 plus één zonder traject in
de naam, een koppeltabel, een aantal aangepaste versies en een AHN-shapefile met dwarsprofielen. Het meegeleverde voorbeeld-ini-bestand wijst
daarnaar, zodat de editor zonder eigen data werkt. Nodig: Python 3.9 of hoger.

1. Haal de code op en ga naar de map:

   ```bash
   git clone https://github.com/MariovdBerg/ProfielEditor.git
   ```

   ```bash
   cd ProfielEditor
   ```

2. Installeer prflcheck (zie [Installatie](#installatie) voor andere manieren):

   ```bash
   python -m pip install -e ".[dev]"
   ```

3. Dubbelklik op **`start_profieleditor.bat`**. Bij deze eerste start wordt `profieleditor.ini` gemaakt als kopie
   van [`profieleditor.voorbeeld.ini`](profieleditor.voorbeeld.ini). De browser opent op
   <http://127.0.0.1:8765/> met de testprofielen in de lijst. Sluit het zwarte venster om de editor te stoppen.

Klik op een dijkvak, sleep een punt in de grafiek en kijk rechtsboven hoe prflcheck reageert. *💾 Opslaan*
(Ctrl+S) schrijft het profiel naar `tests\test_prfl_aangepast\`. Dat is testdata die in git staat: met
`git checkout tests` zet je die terug.

Voor een eigen traject: vul in `profieleditor.ini` (of via **⚙ Instellingen** in de editor) je eigen
profielmap, koppeltabel en uitvoermap in; zie [Instellingen](#instellingen) en [Invoer](#invoer).

## Installatie

De editor zelf hoeft niet geïnstalleerd te worden: hij draait vanuit de checkout. Alleen prflcheck
([ProfielCheckPython](https://github.com/MariovdBerg/ProfielCheckPython)) is nodig. Dat staat niet op PyPI en
wordt van GitHub geïnstalleerd, vastgezet op release `v2.0.0` (zie `pyproject.toml`), omdat de editor de
grenswaarden van de controle uit prflcheck overneemt.

Vanuit de checkout van de editor (met pytest en ruff voor het [testen](#ontwikkelen-en-testen)):

```bash
python -m pip install -e ".[dev]"
```

Of alleen prflcheck:

```bash
python -m pip install "prflcheck @ git+https://github.com/MariovdBerg/ProfielCheckPython.git@v2.0.0"
```

Gebruik `python -m pip`: een losse `pip` kan bij een andere Python horen dan de Python die de editor start.

**Zonder installatie van prflcheck** gebruikt de editor de broncode uit een clone van ProfielCheckPython:

1. de map uit `PRFLCHECK_PATH`, als die is ingevuld;
2. anders `..\ProfielCheckPython\src`, een clone naast deze map. Die wordt vanzelf gevonden.

`PRFLCHECK_PATH` staat bovenaan in `start_profieleditor.bat` en is leeg na een checkout. Vul het alleen in als de
clone ergens anders staat, bijvoorbeeld op een netwerkschijf, en laat het verwijzen naar de map `src` (waarin de
map `prflcheck` staat), niet naar de map van de repository zelf:

```bat
set "PRFLCHECK_PATH=D:\GitHub\ProfielCheckPython\src"
```

Een geïnstalleerde prflcheck gaat altijd voor; `PRFLCHECK_PATH` wordt dan niet gebruikt. Bij het starten staat in
het venster welke prflcheck (versie en map) de editor gebruikt. Wie `src\app.py` zonder de `.bat` start, kan
`PRFLCHECK_PATH` als omgevingsvariabele zetten.

**Welke Python?** `start_profieleditor.bat` zoekt zelf een Python 3: de `py`-launcher, `python` op het PATH, of
Miniforge/Anaconda/python.org in de standaardmappen. Een vaste Python geef je op bovenaan in de `.bat`:

```bat
set "PYTHON=C:\ProgramData\miniforge3\python.exe"
```

## Instellingen

### Het ini-bestand

De instellingen staan in `profieleditor.ini` in de hoofdmap (naast `start_profieleditor.bat`). Dat bestand staat niet in git: bij de eerste start
wordt het gemaakt als kopie van [`profieleditor.voorbeeld.ini`](profieleditor.voorbeeld.ini), dat naar de
testdata in `tests\` wijst (je kunt het ook zelf kopiëren). Vul daarin je eigen paden in:

```ini
[paden]
prfl_map = C:\pad\naar\profielen
koppeltabel = C:\pad\naar\koppeling.xlsx
uitvoer_map = C:\pad\naar\profielen_aangepast
ahn_shapefile = C:\pad\naar\cross_lines_ahn.shp
```

Aanhalingstekens zijn niet nodig, ook niet bij spaties in een pad. Relatieve paden gelden ten opzichte van de
map van het `.ini`-bestand. Commentaar begint met `;`.

| Sectie | Instelling | Standaard | Betekenis |
|---|---|---|---|
| `[paden]` | `prfl_map` | (verplicht) | map met de originele `.prfl`-bestanden |
| | `koppeltabel` | leeg (= alle profielen in de map) | koppeltabel dijkvak ↔ profiel (`.csv` of `.xlsx`); zie [Koppeltabel](#koppeltabel) |
| | `uitvoer_map` | leeg (= de prfl-map) | map voor aangepaste profielen |
| | `ahn_shapefile` | leeg (= geen) | PolylineZ-shapefile met AHN-dwarsprofielen; zie [AHN-shapefile](#ahn-shapefile) |
| `[opties]` | `achtervoegsel` | `_aangepast` | achtervoegsel van aangepaste bestanden: `34-1_145.prfl` → `34-1_145_aangepast.prfl` |
| | `versie` | `4` | bestandsversie bij opslaan: `3` of `4` |
| | `kolom_traject`, `kolom_dijkvak`, `kolom_profiel` | leeg (= automatisch) | kolomnamen in de koppeltabel; `-` = kolom niet gebruiken |
| | `ahn_kolom_traject`, `ahn_kolom_dijkvak`, `ahn_kolom_profiel` | leeg (= automatisch) | kolomnamen in de AHN-shapefile; `-` = niet gebruiken |
| | `poort` | `8765` | poort van de lokale server; is die bezet, dan de volgende vrije |

De instellingen zijn ook in de editor aan te passen via **⚙ Instellingen** (met *Bladeren…*). Wat daar verandert,
wordt in het `.ini`-bestand bewaard; alleen de gewijzigde regels worden aangepast, commentaar blijft staan. Een
map of koppeltabel uit het `.ini`-bestand die niet bestaat, geeft een waarschuwing en opent de instellingen.

**Een ander `.ini`-bestand** (bijvoorbeeld per project): sleep het `.ini`-bestand op `start_profieleditor.bat`, of

```bat
start_profieleditor.bat C:\project\profieleditor.ini
```

Een snelkoppeling naar de `.bat` met het `.ini`-bestand als argument werkt ook.

### Opdrachtregel

Zonder het `.bat`-bestand:

```bash
python src\app.py [--ini profieleditor.ini] [opties]
```

Zonder `--ini` wordt `profieleditor.ini` in de hoofdmap gebruikt (de map boven `src`, ook als je `app.py` vanuit
een andere map start); bestaat dat nog niet, dan wordt het eerst
gemaakt uit `profieleditor.voorbeeld.ini`. Opties op de opdrachtregel gaan voor het `.ini`-bestand:

| Optie | Betekenis |
|---|---|
| `--ini` | instellingenbestand |
| `--prfl-map` | map met de `.prfl`-bestanden |
| `--koppeltabel` | koppeltabel dijkvak ↔ profiel (`.csv` of `.xlsx`, optioneel) |
| `--uitvoer-map` | map voor aangepaste profielen (standaard: de prfl-map) |
| `--achtervoegsel` | achtervoegsel van aangepaste bestanden (standaard `_aangepast`) |
| `--versie` | bestandsversie bij opslaan: 3 of 4 (standaard 4) |
| `--kolom-dijkvak`, `--kolom-profiel`, `--kolom-traject` | kolomnamen in de koppeltabel, als de automatische herkenning niet werkt |
| `--ahn-shapefile` | AHN-shapefile (PolylineZ) voor de achtergrond van de grafiek |
| `--ahn-kolom-traject`, `--ahn-kolom-dijkvak`, `--ahn-kolom-profiel` | kolomnamen in de AHN-shapefile |
| `--poort` | poort van de server (standaard 8765; is die bezet, dan de volgende vrije) |
| `--geen-browser` | browser niet automatisch openen |

## Invoer

Wat je aanlevert, in het kort:

| Invoer | Verplicht | Instelling |
|---|---|---|
| Profielen: een map met `.prfl`-bestanden | ja | `prfl_map` |
| Koppeltabel: dijkvak ↔ profiel | nee; zonder tabel worden alle profielen in de map getoond | `koppeltabel`, `kolom_*` |
| Uitvoermap: aangepaste profielen | nee; standaard de prfl-map | `uitvoer_map`, `achtervoegsel` |
| AHN-shapefile: hoogtes op de achtergrond | nee | `ahn_shapefile`, `ahn_kolom_*` |

### Profielen

De map `prfl_map` bevat de originele profielen, in een formaat dat prflcheck kan lezen (versie 3 of 4). De
bestandsnaam heeft bij voorkeur de vorm `{traject}_{dijkvak}[_tekst].prfl`, bijvoorbeeld `34-1_145.prfl`: dan
vindt de editor traject en dijkvak ook zonder koppeltabel (zie hieronder).

### Koppeltabel

Een tabel met een kopregel; per regel één dijkvak en (optioneel) het traject en het profiel:

```
traject;dijkvak;profiel;opmerking
34-1;145;34-1_145.prfl;
34-1;147;34-1_147;bestandsnaam mag zonder .prfl
;15;35-2_15.prfl;traject leeg: uit de bestandsnaam (35-2)
```

- **Bestandsformaat:** CSV met `;`, `,` of tab als scheidingsteken, UTF-8 of cp1252. Bij `.xlsx` wordt het eerste
  werkblad gelezen.
- **Kolommen** worden op naam herkend (hoofdletterongevoelig), of vast ingesteld met `kolom_traject`,
  `kolom_dijkvak` en `kolom_profiel` in het `.ini`-bestand (`-` = kolom niet gebruiken):

  | Kolom | Herkend als | Anders |
  |---|---|---|
  | traject | `traject`, `traject_id` of `dijktraject` (of bevat "traject") | optioneel |
  | dijkvak | `dijkvak`, `dijkvak_id`, `vak_id` of `vak` (of bevat "vak") | de eerste kolom |
  | profiel | `profiel`, `prfl`, `bestand` of `bestandsnaam` (of bevat "prfl"/"profiel") | de eerste overige kolom |

- **Profiel:** een bestandsnaam in de prfl-map, met of zonder `.prfl`. Is de cel leeg, dan wordt er niet naar
  een bestand gezocht: het dijkvak staat in de lijst als *ontbreekt* ("Geen profiel opgegeven in de koppeltabel").
- **Traject en dijkvak** worden in deze volgorde bepaald:
  1. uit de koppeltabel;
  2. wat daar leeg is, uit de bestandsnaam `{traject}_{dijkvak}[_tekst].prfl`, alleen als het eerste deel op een
     traject lijkt (`34-1`, `34a-1`, `35-2`, …). Bij `35-2_6_damwand.prfl` is dat traject 35-2, dijkvak 6;
  3. lukt dat niet (bijvoorbeeld `dijk_noord.prfl`), dan is het traject en/of dijkvak *onbekend*.

  Bij een tegenstrijdigheid wint de koppeltabel. Een dijkvak heet `{traject}_{dijkvak}` (bijvoorbeeld `34-1_145`),
  zodat gelijke vaknummers in verschillende trajecten uit elkaar worden gehouden. Wat uit de bestandsnaam komt, is
  gemarkeerd met *uit naam*. Wijkt de `ID` in het profiel af van `{traject}_{dijkvak}`, dan staat er *ID ≠* bij.
- **Overige kolommen** worden als informatie bij het dijkvak getoond (tab *Profiel*).
- **Profielen die niet in de koppeltabel staan**, staan ook in de lijst (bij hun traject uit de bestandsnaam,
  gemarkeerd met *niet in koppeltabel*). Zonder koppeltabel worden alle profielen in de map getoond.

### Aangepaste versies

Bij elk origineel `{naam}.prfl` worden de aangepaste versies in de uitvoermap gezocht:

1. `{naam}{achtervoegsel}.prfl`, met het achtervoegsel uit het `.ini`-bestand (standaard `_aangepast`).
2. Alleen voor originelen zonder zo'n bestand: elk overgebleven bestand waarvan de naam begint met `{naam}`, gevolgd
   door een scheidingsteken (`_` `-` `.` of spatie) of niets. Alles na `{naam}` is het achtervoegsel, bijvoorbeeld
   `35-2_6_damwand.prfl` → `_damwand`. Past een bestand bij meerdere originelen (`34-1_14` en `34-1_145`), dan hoort
   het bij het langste. `34-1_1450.prfl` hoort niet bij `34-1_145` (geen scheidingsteken).
3. Heeft een bestand precies dezelfde naam als het origineel, dan is het de aangepaste versie, gemarkeerd als
   *dubbele naam*.

Zijn er meerdere versies (*N VERSIES* in de lijst), dan wordt de nieuwste geopend; een andere versie of het
origineel kies je in de keuzelijst bovenin. Staan originelen en aangepaste profielen in dezelfde map, dan zijn de
profielen uit de koppeltabel de originelen en kunnen de overige bestanden versies zijn; een bestand is nooit een
versie van zichzelf.

### AHN-shapefile

Met `ahn_shapefile` worden AHN-dwarsprofielen achter het profiel getekend. Gebruik een **PolylineZ**-shapefile met
de `.dbf` ernaast, zoals `cross_lines_ahn.shp` uit [AHNProfielCreator](https://github.com/MariovdBerg/AHNProfielCreator).
Een shapefile zonder hoogtes (zoals `cross_lines.shp`) geeft een melding. De shapefile wordt één keer ingelezen
(ca. 1,5 s voor 6624 lijnen) en opnieuw als het bestand verandert.

**Koppelen** – kolommen `ahn_kolom_traject`, `ahn_kolom_dijkvak` en `ahn_kolom_profiel` (leeg = automatisch
herkennen met dezelfde namen als de koppeltabel, bijvoorbeeld `TRAJECT_ID` en `vak_id`; `-` = niet gebruiken).
Per lijn:

1. Wijst de profielkolom een bekend profiel aan, dan hoort de lijn bij dat profiel (de shapefile wordt gevolgd).
   Wijken traject of dijkvak van de lijn af van die van het profiel, dan staat er *AHN ≠* bij het profiel, met
   een waarschuwing in de grafiek.
2. Anders moeten traject en dijkvak van de lijn **exact** gelijk zijn aan die van het profiel (zonder trajectkolom
   alleen het dijkvak). Bevat de dijkvak-kolom traject en dijkvak samen (`34-1_145`), dan is dat niet gelijk aan
   dijkvak `145` uit de koppeltabel en wordt er niets gekoppeld. In `tests\test_shapefiles` bevat `vak_id` alleen
   het dijkvak (`145`), voor de 11 testprofielen in `tests\test_prfl_origineel`.

Onder de lijst staat hoeveel lijnen gekoppeld zijn, met voorbeelden van lijnen die nergens bij passen. Heeft een
profiel geen lijnen, dan staat in de grafiek waarop gezocht is. *⚙ Instellingen* toont de kolommen van de
shapefile.

**Tekenen** – x is de afstand langs de lijn min de halve lijnlengte (x = 0 in het midden van de lijn), z de
AHN-hoogte; punten zonder hoogte (-99999) en gaten worden niet getekend. Alle lijnen zijn even licht en liggen
achter het profiel. Zie [Grafiek](#grafiek) voor aan/uit en spiegelen.

## Gebruik

Start de editor met `start_profieleditor.bat` (of `python src\app.py`, zie [Opdrachtregel](#opdrachtregel)). De
editor opent in de browser op <http://127.0.0.1:8765/> en is alleen bereikbaar vanaf de eigen computer. Stoppen:
sluit het zwarte venster of druk Ctrl+C. Sluit je de browser met niet-opgeslagen wijzigingen, dan vraagt de
browser eerst om bevestiging.

### Lijst met dijkvakken

- Links staan alle dijkvakken, per traject gegroepeerd (*Traject onbekend* als laatste), met de
  prflcheck-status: groen = ok, rood = foutcode, open rondje = profiel ontbreekt.
- Zoeken, filteren op traject en op *Met fout*, *Aangepast* en *Niet aangepast*.
- ◀ ▶ of PageUp/PageDown bladert naar het vorige of volgende profiel.
- Markeringen: *uit naam*, *ID ≠*, *niet in koppeltabel*, *N VERSIES*, *dubbele naam* en *AHN ≠*; zie
  [Invoer](#invoer).

### Grafiek

- **Selecteren en verplaatsen:** klik op een punt om het te selecteren. LMB-slepen verplaatst langs x, RMB-slepen
  langs z, Shift+slepen vrij. Pijltjestoetsen verschuiven het geselecteerde punt 0,01 m (Shift: 0,1 m,
  Alt: 0,001 m).
- **Punten:** dubbelklik op een lijn voegt daar een punt in. *＋ Punt* voegt een punt in na het geselecteerde punt,
  *✕ Punt* verwijdert het.
- **Zoomen en schuiven:** scrollen zoomt (Shift: alleen x, Ctrl: alleen z), slepen op een leeg vlak schuift het
  beeld. *⛶ Passend* (F) past het beeld op het profiel, niet op de AHN-lijnen.
- **Kleuren:** taluddelen oranje, bermen groen, voorland gestreept, ongeldige delen rood (volgens de regels van
  prflcheck); de helling staat als 1:n bij elk deel. Het originele profiel staat gestreept grijs op de achtergrond.
- **Voorland:** *＋ Voorlandpunt* voegt een punt vóór het eerste punt toe; *Teen hier* maakt het geselecteerde punt
  de teen (laatste voorlandpunt = eerste dijkpunt). Het aantal voorlandpunten staat ook in de tab *Profiel*.
- **AHN:** *AHN* zet de AHN-lijnen aan of uit. *Spiegel AHN* spiegelt ze (x → −x) voor het geopende profiel,
  bijvoorbeeld als de lijn andersom is getekend; die keuze geldt tot de pagina wordt herladen.
- **Profielcheck:** bij elke wijziging wordt het profiel direct gecontroleerd met prflcheck (rechtsboven).
- **Tabs:** *Punten* met de coördinaten, *Profiel* met ID, kruinhoogte, richting, dam, damhoogte, damwand, memo
  en de extra kolommen uit de koppeltabel, en *Opslaan*.
- *↺ Origineel* zet de punten van het originele profiel terug. Ongedaan maken / opnieuw met ↶ ↷.

### Opslaan

*💾 Opslaan* (Ctrl+S) schrijft naar de uitvoermap, in versie 3 of 4:

- naar de geopende aangepaste versie, of
- naar `{naam}{achtervoegsel}.prfl` als het origineel geopend is.

Bestaat het bestand al, dan wordt eerst gevraagd of het overschreven mag worden. *⬇ Download* en *Voorbeeld*
geven de `.prfl`-tekst zonder op te slaan.

### Sneltoetsen

| Toets | Actie |
|---|---|
| Ctrl+S | opslaan |
| Ctrl+Z / Ctrl+Y (of Ctrl+Shift+Z) | ongedaan maken / opnieuw |
| PageUp / PageDown | vorig / volgend profiel |
| Tab / Shift+Tab | volgend / vorig punt selecteren |
| Pijltjestoetsen | geselecteerd punt 0,01 m verschuiven (Shift: 0,1 m, Alt: 0,001 m) |
| Insert of + | punt invoegen na het geselecteerde punt |
| Delete of Backspace | geselecteerd punt verwijderen |
| F | passend weergeven |

## Uitvoer

Opslaan schrijft altijd naar de uitvoermap. Met een aparte uitvoermap blijven de originelen in de prfl-map dus
ongewijzigd.

| Bestand | Inhoud |
|---|---|
| `<uitvoer_map>\{naam}{achtervoegsel}.prfl` | aangepast profiel, bijvoorbeeld `34-1_145_aangepast.prfl` |
| `<uitvoer_map>\{naam}_{tekst}.prfl` | een bestaande versie met een ander achtervoegsel die geopend en opgeslagen is, bijvoorbeeld `35-2_6_damwand.prfl` |

Daarnaast bewaart de editor gewijzigde instellingen in het gebruikte `.ini`-bestand.

## Ontwikkelen en testen

```bash
python -m pip install -e ".[dev]"
```

```bash
python -m pytest
```

```bash
ruff check .
```

| Bestand | Inhoud |
|---|---|
| `src\app.py` | webserver, instellingen en de API voor de pagina |
| `src\koppeling.py` | inlezen van de koppeltabel (`.csv` en `.xlsx`, alleen standaardbibliotheek) |
| `src\identificatie.py` | traject en dijkvak uit de bestandsnaam, zoeken van aangepaste versies |
| `src\ahn.py` | inlezen en koppelen van de AHN-shapefile (alleen standaardbibliotheek) |
| `src\static\` | de pagina: `index.html`, `app.js`, `style.css` |
| `tests\` | tests en testdata |
| `start_profieleditor.bat`, `profieleditor.voorbeeld.ini` | starten en standaardinstellingen, in de hoofdmap |

De modules in `src\` worden als losse modules geïmporteerd (`import app`); pytest zet `src` daarvoor op het pad
(`pythonpath` in `pyproject.toml`). Na het verplaatsen naar `src\` moet een bestaande editable installatie opnieuw:
`python -m pip install -e ".[dev]"`.

`tests\test_constanten.py` controleert dat de grenswaarden waarmee de editor profieldelen kleurt
(`src\static\app.js`) gelijk zijn aan die in `prflcheck.checks`.

## Licentie

Copyright © 2026 HKV lijn in water B.V.

De Profieleditor valt onder de [European Union Public Licence v1.2](LICENSE) (EUPL-1.2), een opensourcelicentie
met copyleft: je mag de code gebruiken, aanpassen en verspreiden, ook commercieel, als je de copyrightvermeldingen
laat staan, de licentie meelevert, je wijzigingen aangeeft en gewijzigde versies onder de EUPL verspreidt (of onder
een verenigbare licentie uit de bijlage ervan). De officiële tekst in alle EU-talen staat op
<https://interoperable-europe.ec.europa.eu/collection/eupl/eupl-text-eupl-12>.

prflcheck ([ProfielCheckPython](https://github.com/MariovdBerg/ProfielCheckPython)) valt ook onder de EUPL-1.2.
