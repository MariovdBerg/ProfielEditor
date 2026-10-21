# Profieleditor

Interactieve editor in de browser voor Hydra-NL/HydraRing-profielen (`.prfl`).
Profielen worden gelezen, gecontroleerd en weggeschreven met [prflcheck](https://github.com/MariovdBerg/ProfielCheckPython); 
een koppeltabel (`.csv` of `.xlsx`) koppelt de profielen aan dijkvakken.

**Auteurs:** Dion Rovers, Ilian de Snoo, Mario van den Berg, Claude  
**Copyright:** © 2026 HKV lijn in water B.V.  
**Licentie:** [EUPL-1.2](https://github.com/MariovdBerg/ProfielEditor/blob/main/LICENSE)

De editor bestaat uit een kleine lokale Python-webserver (`app.py`, alleen standaardbibliotheek)
en een HTML/JavaScript-pagina (`static/`). Er zijn geen andere afhankelijkheden dan prflcheck.

## Starten

1. De instellingen staan in `profieleditor.ini` naast `app.py`. Dat bestand staat niet in git: bij de eerste
   start wordt het gemaakt als kopie van [`profieleditor.voorbeeld.ini`](profieleditor.voorbeeld.ini), dat naar
   de testdata in `tests\` wijst (je kunt het ook zelf kopiëren). Vul daarin je eigen paden in:

   ```ini
   [paden]
   prfl_map = C:\pad\naar\profielen
   koppeltabel = C:\pad\naar\koppeling.xlsx
   uitvoer_map = C:\pad\naar\profielen_aangepast
   ahn_shapefile = C:\pad\naar\cross_lines_ahn.shp
   ```

   Aanhalingstekens zijn niet nodig. Relatieve paden gelden ten opzichte van de map van het `.ini`-bestand.
   In de sectie `[opties]` staan achtervoegsel, bestandsversie, kolomnamen en poort.

2. Dubbelklik op **`start_profieleditor.bat`**. Die zoekt Python 3 (de `py`-launcher, `python` op het PATH,
   of Miniforge/Anaconda/python.org in de standaardmappen), start de server en opent de editor in de browser
   op `http://127.0.0.1:8765/`. Sluit het zwarte venster om de editor te stoppen.

   - Een vaste Python opgeven: zet bovenaan in de `.bat` `set "PYTHON=C:\...\python.exe"`.
   - Een ander `.ini`-bestand (bijvoorbeeld per project): sleep het `.ini`-bestand op de `.bat`, of
     `start_profieleditor.bat C:\project\profieleditor.ini`. Een snelkoppeling naar de `.bat` met het
     `.ini`-bestand als argument werkt ook.

**prflcheck** staat niet op PyPI en wordt van GitHub geïnstalleerd, vastgezet op release `v2.0.0`
(zie `pyproject.toml`). Vanuit de checkout van de editor:

```bash
pip install -e ".[dev]"
```

Of alleen prflcheck:

```bash
pip install "prflcheck @ git+https://github.com/MariovdBerg/ProfielCheckPython.git@v2.0.0"
```

Is prflcheck niet in Python geïnstalleerd, dan gebruikt de editor de broncode uit een clone van
[ProfielCheckPython](https://github.com/MariovdBerg/ProfielCheckPython):

1. de map uit `PRFLCHECK_PATH`, als die is ingevuld;
2. anders `..\ProfielCheckPython\src`, een clone naast deze map. Die wordt vanzelf gevonden.

`PRFLCHECK_PATH` staat bovenaan in `start_profieleditor.bat` en is leeg na een checkout. Vul het alleen in als de
clone ergens anders staat, bijvoorbeeld op een netwerkschijf, en laat het verwijzen naar de map `src` (waarin de
map `prflcheck` staat), niet naar de map van de repository zelf:

```bat
set "PRFLCHECK_PATH=D:\GitHub\ProfielCheckPython\src"
```

Een geïnstalleerde prflcheck gaat altijd voor; `PRFLCHECK_PATH` wordt dan niet gebruikt. Bij het starten staat in het
venster welke prflcheck (versie en map) de editor gebruikt. Wie `app.py` zonder de `.bat` start, kan
`PRFLCHECK_PATH` als omgevingsvariabele zetten.

De instellingen zijn ook in de editor aan te passen via **⚙ Instellingen** (met *Bladeren…*).
Wat daar verandert, wordt in het `.ini`-bestand bewaard; alleen de gewijzigde regels worden aangepast,
commentaar blijft staan. Een map of koppeltabel uit het `.ini`-bestand die niet bestaat, geeft een
waarschuwing en opent de instellingen.

### Opdrachtregel

```bash
python app.py [--ini profieleditor.ini] [opties]
```

Zonder `--ini` wordt `profieleditor.ini` naast `app.py` gebruikt; bestaat dat nog niet, dan wordt het eerst
gemaakt uit `profieleditor.voorbeeld.ini`.
Opties op de opdrachtregel gaan voor het `.ini`-bestand:

| Optie | Betekenis |
|---|---|
| `--ini` | Instellingenbestand |
| `--prfl-map` | Map met de `.prfl`-bestanden |
| `--koppeltabel` | Koppeltabel dijkvak ↔ profiel (`.csv` of `.xlsx`, optioneel) |
| `--uitvoer-map` | Map voor aangepaste profielen (standaard: de prfl-map) |
| `--achtervoegsel` | Achtervoegsel van aangepaste bestanden (standaard `_aangepast`) |
| `--versie` | Bestandsversie bij opslaan: 3 of 4 (standaard 4) |
| `--kolom-dijkvak`, `--kolom-profiel`, `--kolom-traject` | Kolomnamen in de koppeltabel, als de automatische herkenning niet werkt |
| `--ahn-shapefile` | AHN-shapefile (PolylineZ) voor de achtergrond van de grafiek |
| `--ahn-kolom-traject`, `--ahn-kolom-dijkvak`, `--ahn-kolom-profiel` | Kolomnamen in de AHN-shapefile |
| `--poort` | Poort van de server (standaard 8765; is die bezet, dan de volgende vrije) |
| `--geen-browser` | Browser niet automatisch openen |

## Koppeltabel

Een tabel met een kopregel; per regel één dijkvak en (optioneel) het traject en het profiel:

```
traject;dijkvak;profiel;opmerking
34-1;145;34-1_145.prfl;
34-1;147;34-1_147;bestandsnaam mag zonder .prfl
;15;35-2_15.prfl;traject leeg: uit de bestandsnaam (35-2)
```

- Kolommen worden op naam herkend (hoofdletterongevoelig), of vast ingesteld met `kolom_traject`,
  `kolom_dijkvak` en `kolom_profiel` in het `.ini`-bestand (`-` = kolom niet gebruiken):
  - traject: `traject`, `traject_id` of `dijktraject` (of bevat "traject"); optioneel
  - dijkvak: `dijkvak`, `dijkvak_id`, `vak_id` of `vak` (of bevat "vak"); anders de eerste kolom
  - profiel: `profiel`, `prfl`, `bestand` of `bestandsnaam` (of bevat "prfl"/"profiel"); anders de eerste overige kolom
- **Profiel:** een bestandsnaam in de prfl-map, met of zonder `.prfl`. Is de cel leeg, dan wordt er niet naar
  een bestand gezocht: het dijkvak staat in de lijst als *ontbreekt* ("Geen profiel opgegeven in de koppeltabel").
- **Traject en dijkvak** worden in deze volgorde bepaald:
  1. uit de koppeltabel;
  2. wat daar leeg is, uit de bestandsnaam `{traject}_{dijkvak}[_tekst].prfl`, alleen als het eerste deel op een
     traject lijkt (`34-1`, `34a-1`, `35-2`, …). Bij `35-2_6_damwand.prfl` is dat traject 35-2, dijkvak 6;
  3. lukt dat niet (bijvoorbeeld `dijk_noord.prfl`), dan is het traject en/of dijkvak *onbekend*.

  Bij een tegenstrijdigheid wint de koppeltabel. Een dijkvak heet `{traject}_{dijkvak}` (bijvoorbeeld `34-1_145`),
  zodat gelijke vaknummers in verschillende trajecten uit elkaar worden gehouden. De lijst is per traject gegroepeerd
  (*Traject onbekend* als laatste) en kan op traject worden gefilterd. Wat uit de bestandsnaam komt, is gemarkeerd
  met *uit naam*. Wijkt de `ID` in het profiel af van `{traject}_{dijkvak}`, dan staat er *ID ≠* bij.
- CSV met `;`, `,` of tab als scheidingsteken, UTF-8 of cp1252. Bij `.xlsx` wordt het eerste werkblad gelezen.
- Overige kolommen worden als informatie bij het dijkvak getoond (tab *Profiel*).
- Profielen in de map die niet in de koppeltabel staan, staan ook in de lijst (bij hun traject uit de bestandsnaam,
  gemarkeerd met *niet in koppeltabel*). Zonder koppeltabel worden alle profielen in de map getoond.

## Aangepaste versies

Bij elk origineel `{naam}.prfl` worden de aangepaste versies in de uitvoermap gezocht:

1. `{naam}{achtervoegsel}.prfl`, met het achtervoegsel uit het `.ini`-bestand (standaard `_aangepast`).
2. Alleen voor originelen zonder zo'n bestand: elk overgebleven bestand waarvan de naam begint met `{naam}`, gevolgd
   door een scheidingsteken (`_` `-` `.` of spatie) of niets. Alles na `{naam}` is het achtervoegsel, bijvoorbeeld
   `35-2_6_damwand.prfl` → `_damwand`. Past een bestand bij meerdere originelen (`34-1_14` en `34-1_145`), dan hoort het
   bij het langste. `34-1_1450.prfl` hoort niet bij `34-1_145` (geen scheidingsteken).
3. Heeft een bestand precies dezelfde naam als het origineel, dan is het de aangepaste versie, gemarkeerd als
   *dubbele naam*.

Zijn er meerdere versies (*N VERSIES* in de lijst), dan wordt de nieuwste geopend; een andere versie of het origineel
kies je in de keuzelijst bovenin. Staan originelen en aangepaste profielen in dezelfde map, dan zijn de profielen uit
de koppeltabel de originelen en kunnen de overige bestanden versies zijn; een bestand is nooit een versie van zichzelf.

## Werking

- **Lijst links:** alle dijkvakken met de prflcheck-status (groen = ok, rood = foutcode, open rondje = profiel
  ontbreekt). Zoeken en filteren op *met fout*, *aangepast* en *niet aangepast*. ◀ ▶ of PageUp/PageDown bladert.
- **Grafiek:** klik op een punt om het te selecteren.
  LMB-slepen verplaatst langs x, RMB-slepen langs z (zoals in de notebook), Shift+slepen vrij.
  Dubbelklik op een lijn voegt daar een punt in. Scrollen zoomt (Shift: alleen x, Ctrl: alleen z),
  slepen op een leeg vlak schuift het beeld. Pijltjestoetsen verschuiven het geselecteerde punt 0,01 m
  (Shift: 0,1 m, Alt: 0,001 m).
- **Kleuren:** taluddelen oranje, bermen groen, voorland gestreept, ongeldige delen rood (volgens de regels van
  prflcheck); de helling staat als 1:n bij elk deel. Het originele profiel staat gestreept grijs op de achtergrond.
- **Voorland:** *＋ Voorlandpunt* voegt een punt vóór het eerste punt toe; *Teen hier* maakt het geselecteerde punt
  de teen (laatste voorlandpunt = eerste dijkpunt). Het aantal voorlandpunten staat ook in de tab *Profiel*.
- **Profielcheck:** bij elke wijziging wordt het profiel direct gecontroleerd met `prflcheck` (rechtsboven).
- **Profiel-tab:** ID, kruinhoogte, richting, dam, damhoogte, damwand en memo.
- **Opslaan** (Ctrl+S): naar de uitvoermap, in versie 3 of 4: naar de geopende aangepaste versie, of
  `{naam}{achtervoegsel}.prfl` als het origineel geopend is. Bestaat het bestand al, dan wordt eerst gevraagd of het
  overschreven mag worden. *↺ Origineel* zet de punten van het originele profiel terug. *Download* en *Voorbeeld* geven de
  `.prfl`-tekst zonder op te slaan.
- Ongedaan maken / opnieuw met Ctrl+Z / Ctrl+Y.

## AHN-achtergrond

Met `ahn_shapefile` (ini of *Instellingen*) worden AHN-dwarsprofielen achter het profiel getekend, zoals in de
notebook. Gebruik een **PolylineZ**-shapefile met de `.dbf` ernaast, bijvoorbeeld `cross_lines_ahn.shp`; een shapefile
zonder hoogtes (zoals `cross_lines.shp`) geeft een melding. De shapefile wordt één keer ingelezen (ca. 1,5 s voor
6624 lijnen) en opnieuw als het bestand verandert.

**Koppelen** – kolommen `ahn_kolom_traject`, `ahn_kolom_dijkvak` en `ahn_kolom_profiel` (leeg = automatisch herkennen
met dezelfde namen als de koppeltabel, bijvoorbeeld `TRAJECT_ID` en `vak_id`; `-` = niet gebruiken). Per lijn:

1. Wijst de profielkolom een bekend profiel aan, dan hoort de lijn bij dat profiel (de shapefile wordt gevolgd).
   Wijken traject of dijkvak van de lijn af van die van het profiel, dan staat er *AHN ≠* bij het profiel, met
   een waarschuwing in de grafiek.
2. Anders moeten traject en dijkvak van de lijn **exact** gelijk zijn aan die van het profiel (zonder trajectkolom
   alleen het dijkvak). Bevat de dijkvak-kolom traject en dijkvak samen (`34-1_145`), dan is dat niet gelijk aan
   dijkvak `145` uit de koppeltabel en wordt er niets gekoppeld. In `tests/test_shapefiles` bevat `vak_id` alleen
   het dijkvak (`145`), voor de 11 testprofielen in `tests/test_prfl_origineel`.

Onder de lijst staat hoeveel lijnen gekoppeld zijn, met voorbeelden van lijnen die nergens bij passen. Heeft een
profiel geen lijnen, dan staat in de grafiek waarop gezocht is. *Instellingen* toont de kolommen van de shapefile.

**Tekenen** – x is de afstand langs de lijn min de halve lijnlengte (x = 0 in het midden van de lijn), z de
AHN-hoogte; punten zonder hoogte (-99999) en gaten worden niet getekend. Alle lijnen even licht, achter het
profiel. *AHN* zet ze aan of uit, *Spiegel AHN* spiegelt ze (x → −x) voor het geopende profiel, bijvoorbeeld als de
lijn andersom is getekend; die keuze geldt tot de pagina wordt herladen. *⛶ Passend* past op het profiel, niet op
de AHN-lijnen.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest
ruff check .
```

`tests/test_constanten.py` controleert dat de grenswaarden waarmee de editor profieldelen kleurt
(`static/app.js`) gelijk zijn aan die in `prflcheck.checks`.

## Licentie

Copyright © 2026 HKV lijn in water B.V.

Licensed under the EUPL

Dit werk valt onder de [European Union Public Licence v1.2](https://github.com/MariovdBerg/ProfielEditor/blob/main/LICENSE)
(EUPL-1.2), een opensourcelicentie met copyleft: je mag de code gebruiken, aanpassen en verspreiden, ook
commercieel, als je de copyrightvermeldingen laat staan, de licentie meelevert, je wijzigingen aangeeft en
gewijzigde versies onder de EUPL verspreidt (of onder een verenigbare licentie uit de bijlage ervan). De officiële
tekst in alle EU-talen staat op <https://interoperable-europe.ec.europa.eu/collection/eupl/eupl-text-eupl-12>.

prflcheck ([ProfielCheckPython](https://github.com/MariovdBerg/ProfielCheckPython)) valt ook onder de EUPL-1.2.
