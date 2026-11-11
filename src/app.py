"""
Profieleditor (HTML) voor Hydra-NL/HydraRing-profielen (.prfl)
Copyright © 2026 HKV lijn in water B.V.
Licensed under the EUPL
SPDX-License-Identifier: EUPL-1.2

Start een lokale webserver met een interactieve profieleditor in de browser.
Profielen worden gelezen, gecontroleerd en weggeschreven met de module prflcheck.
Een koppeltabel (.csv of .xlsx) koppelt de profielen aan dijkvakken.

Gebruik:
    start_profieleditor.bat                  (leest profieleditor.ini in de hoofdmap, zie profieleditor.voorbeeld.ini)
    python src/app.py [--ini instellingen.ini] [--prfl-map <map>] [--koppeltabel <bestand>] [--uitvoer-map <map>]

De broncode staat in src/; de hoofdmap (de map boven src/) bevat de .ini-bestanden en start_profieleditor.bat.

Opties op de opdrachtregel gaan voor het .ini-bestand. Instellingen die in de editor worden
aangepast, worden in het .ini-bestand bewaard.
"""

from __future__ import annotations

import argparse
import configparser
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOOFDMAP = Path(__file__).resolve().parent.parent  # map van de checkout, met src/, de .ini-bestanden en de .bat

try:
    import prflcheck
except ImportError:  # prflcheck niet geïnstalleerd: zoek de broncode naast deze repository
    _bron = os.environ.get("PRFLCHECK_PATH") or str(HOOFDMAP.parent / "ProfielCheckPython" / "src")
    sys.path.insert(0, _bron)
    try:
        import prflcheck
    except ImportError:
        if os.environ.get("PRFLCHECK_PATH"):
            _clone = (f"of laat PRFLCHECK_PATH ({_bron}) verwijzen naar de map src van de clone van "
                      "ProfielCheckPython (met daarin de map prflcheck).")
        else:
            _clone = (f"of zet een clone van ProfielCheckPython zó neer dat de broncode in {_bron} staat, "
                      "of vul PRFLCHECK_PATH in bovenaan start_profieleditor.bat.")
        sys.exit("prflcheck is niet gevonden. Installeer het van GitHub:\n"
                 '    pip install "prflcheck @ git+https://github.com/MariovdBerg/ProfielCheckPython.git@v2.0.0"\n'
                 + _clone)

from prflcheck import DamType, Damwandmodule, Profiel, ProfielError, ProfielPunt, ProfielVersion

from ahn import AhnBestand, kies_kolommen, koppel, lees_shapefile
from identificatie import identificeer, koppel_versies
from koppeling import Koppeling, lees_koppeltabel

logger = logging.getLogger("profieleditor")

STATIC_MAP = Path(__file__).resolve().parent / "static"
MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png"}


# ── Omzetten tussen Profiel en JSON ────────────────────────────────────────────
def _getal(waarde):
    """float voor JSON: NaN wordt None."""
    return None if waarde is None or (isinstance(waarde, float) and math.isnan(waarde)) else waarde


def _float(waarde):
    """float uit JSON: None of '' wordt NaN."""
    if waarde is None or waarde == "":
        return math.nan
    return float(waarde)


def _enumwaarde(waarde):
    return waarde.value if isinstance(waarde, (DamType, Damwandmodule)) else waarde


def profiel_naar_json(profiel: Profiel) -> dict:
    """Het profiel als dict; de punten als één lijst van voorland tot kruin (teen één keer)."""
    return {
        "id": profiel.id,
        "versie": profiel.versie,
        "damtype": _enumwaarde(profiel.damtype),
        "damhoogte": _getal(profiel.damhoogte),
        "richting": _getal(profiel.richting),
        "kruinhoogte": _getal(profiel.kruinhoogte),
        "damwand": _enumwaarde(profiel.damwand),
        "voorland": profiel.voorland,
        "punten": [[p.x, p.z, _getal(p.r)] for p in profiel.profiel_punten],
        "memo": profiel.memo,
        "invoerfouten": list(profiel.invoerfouten),
    }


def json_naar_profiel(data: dict) -> Profiel:
    """Maak een Profiel uit de dict van profiel_naar_json (zoals de editor die terugstuurt)."""
    punten = [ProfielPunt(float(x), float(z), _float(r)) for x, z, r in data.get("punten", [])]
    return Profiel.from_punten(
        punten,
        voorland=int(data.get("voorland") or 0),
        id=str(data.get("id") or "").strip(),
        damtype=int(data.get("damtype") or 0),
        damhoogte=_float(data.get("damhoogte")),
        richting=_float(data.get("richting")),
        kruinhoogte=_float(data.get("kruinhoogte")),
        damwand=int(data.get("damwand") or 0),
        memo=str(data.get("memo") or ""),
    )


def check_naar_json(fout: ProfielError) -> dict:
    return {"ok": fout == ProfielError.OK, "code": fout.code, "naam": fout.name, "omschrijving": fout.description}


# ── Werkruimte: mappen, koppeltabel en uitvoer ─────────────────────────────────
@dataclass
class _Index:
    bestanden: dict   # bestandsnaam in de bronmap -> pad
    tabel: object     # Koppeltabel of None
    regels: list      # (Koppeling, sleutel of None) per regel van de koppeltabel
    gekoppeld: set    # sleutels die in de koppeltabel staan
    versies: dict     # sleutel van een origineel -> [Versie], nieuwste eerst
    als_versie: set   # bestanden in de bronmap die een versie van een ander profiel zijn


class Werkruimte:
    """Instellingen en bestandstoegang van de editor."""

    def __init__(self, prfl_map="", koppeltabel="", uitvoer_map="", achtervoegsel="_aangepast", versie=4,
                 kolom_dijkvak="", kolom_profiel="", kolom_traject="", ahn_shapefile="", ahn_kolom_traject="",
                 ahn_kolom_dijkvak="", ahn_kolom_profiel="", ini_pad=None):
        self.lock = threading.Lock()
        self.ini_pad = ini_pad  # wijzigingen via de editor worden hierin bewaard (None = niet bewaren)
        self.prfl_map = prfl_map
        self.koppeltabel = koppeltabel
        self.uitvoer_map = uitvoer_map
        self.achtervoegsel = achtervoegsel
        self.versie = versie
        self.kolom_dijkvak = kolom_dijkvak
        self.kolom_profiel = kolom_profiel
        self.kolom_traject = kolom_traject
        self.ahn_shapefile = ahn_shapefile
        self.ahn_kolom_traject = ahn_kolom_traject
        self.ahn_kolom_dijkvak = ahn_kolom_dijkvak
        self.ahn_kolom_profiel = ahn_kolom_profiel
        self._ahn = None            # (sleutel, AhnBestand): ingelezen shapefile, zolang die niet verandert
        self._ahn_koppeling = None  # (AhnKoppeling of None, info) van het laatste overzicht
        self._tabel = None          # (sleutel, Koppeltabel): ingelezen koppeltabel, zolang die niet verandert

    def instellingen(self):
        return {
            "prfl_map": self.prfl_map,
            "koppeltabel": self.koppeltabel,
            "uitvoer_map": self.uitvoer_map,
            "achtervoegsel": self.achtervoegsel,
            "versie": self.versie,
            "kolom_dijkvak": self.kolom_dijkvak,
            "kolom_profiel": self.kolom_profiel,
            "kolom_traject": self.kolom_traject,
            "ahn_shapefile": self.ahn_shapefile,
            "ahn_kolom_traject": self.ahn_kolom_traject,
            "ahn_kolom_dijkvak": self.ahn_kolom_dijkvak,
            "ahn_kolom_profiel": self.ahn_kolom_profiel,
            "ini": str(Path(self.ini_pad).resolve()) if self.ini_pad else "",
        }

    def pas_aan(self, data: dict) -> dict:
        """Pas de instellingen aan; geeft de opgegeven instellingen terug die daardoor zijn veranderd."""
        oud = self.instellingen()
        prfl_map = str(data.get("prfl_map", self.prfl_map)).strip().strip('"')
        koppeltabel = str(data.get("koppeltabel", self.koppeltabel)).strip().strip('"')
        uitvoer_map = str(data.get("uitvoer_map", self.uitvoer_map)).strip().strip('"')
        if prfl_map and not Path(prfl_map).is_dir():
            raise ValueError(f"Map met .prfl-bestanden bestaat niet: {prfl_map}")
        if koppeltabel and not Path(koppeltabel).is_file():
            raise ValueError(f"Koppeltabel bestaat niet: {koppeltabel}")
        ahn_shapefile = str(data.get("ahn_shapefile", self.ahn_shapefile)).strip().strip('"')
        if ahn_shapefile and not Path(ahn_shapefile).is_file():
            raise ValueError(f"AHN-shapefile bestaat niet: {ahn_shapefile}")
        if ahn_shapefile and Path(ahn_shapefile).suffix.lower() != ".shp":
            raise ValueError(f"De AHN-shapefile moet een .shp-bestand zijn: {ahn_shapefile}")
        versie = int(data.get("versie", self.versie))
        if versie not in (3, 4):
            raise ValueError("Versie moet 3 of 4 zijn")
        self.prfl_map, self.koppeltabel, self.uitvoer_map, self.versie = prfl_map, koppeltabel, uitvoer_map, versie
        self.achtervoegsel = str(data.get("achtervoegsel", self.achtervoegsel))
        self.kolom_dijkvak = str(data.get("kolom_dijkvak", self.kolom_dijkvak)).strip()
        self.kolom_profiel = str(data.get("kolom_profiel", self.kolom_profiel)).strip()
        self.kolom_traject = str(data.get("kolom_traject", self.kolom_traject)).strip()
        self.ahn_shapefile = ahn_shapefile
        for sleutel in ("ahn_kolom_traject", "ahn_kolom_dijkvak", "ahn_kolom_profiel"):
            setattr(self, sleutel, str(data.get(sleutel, getattr(self, sleutel))).strip())
        self._ahn_koppeling = None
        nieuw = self.instellingen()
        return {k: nieuw[k] for k in data if k in nieuw and k != "ini" and str(nieuw[k]) != str(oud[k])}

    # -- paden --
    @property
    def bronmap(self) -> Path:
        if not self.prfl_map:
            raise ValueError("Geen map met .prfl-bestanden ingesteld")
        return Path(self.prfl_map).resolve()

    @property
    def doelmap(self) -> Path:
        return Path(self.uitvoer_map).resolve() if self.uitvoer_map else self.bronmap

    def bronpad(self, sleutel: str) -> Path:
        """Pad van een profiel in de bronmap; sleutels buiten de bronmap worden geweigerd."""
        pad = (self.bronmap / sleutel).resolve()
        if self.bronmap not in pad.parents:
            raise ValueError(f"Ongeldig profiel: {sleutel}")
        return pad

    def standaard_uitvoernaam(self, sleutel: str) -> str:
        """Bestandsnaam voor een profiel dat nog geen aangepaste versie heeft: {naam}{achtervoegsel}.prfl."""
        return f"{Path(sleutel).stem}{self.achtervoegsel}.prfl"

    def uitvoerpad(self, bestandsnaam: str) -> Path:
        naam = Path(bestandsnaam).name
        if naam != bestandsnaam or not naam.lower().endswith(".prfl"):
            raise ValueError("De bestandsnaam moet een naam zonder map zijn en eindigen op .prfl")
        return self.doelmap / naam

    # -- koppeltabel, bestanden en versies --
    def _zoek_profiel(self, koppeling, bestanden: dict) -> str | None:
        """Sleutel van het profiel uit de koppeltabel: bestandsnaam, met of zonder .prfl, of een pad in de bronmap."""
        waarde = koppeling.profiel.strip().strip('"').replace("\\", "/")
        if not waarde:
            return None  # geen profiel opgegeven: niet raden naar een bestandsnaam
        kandidaten = [waarde, f"{waarde}.prfl"]
        try:
            kandidaten.insert(0, Path(waarde).resolve().relative_to(self.bronmap).as_posix())
        except (ValueError, OSError):
            pass
        lager = {k.lower(): k for k in bestanden}
        return next((lager[k.lower()] for k in kandidaten if k.lower() in lager), None)

    def _koppeltabel(self):
        """De ingelezen koppeltabel; opnieuw ingelezen als het bestand of de kolominstellingen veranderen."""
        pad = Path(self.koppeltabel).resolve()
        stat = pad.stat()
        sleutel = (str(pad), stat.st_mtime_ns, stat.st_size, self.kolom_dijkvak, self.kolom_profiel,
                   self.kolom_traject)
        if not self._tabel or self._tabel[0] != sleutel:
            tabel = lees_koppeltabel(pad, self.kolom_dijkvak or None, self.kolom_profiel or None,
                                     self.kolom_traject or None)
            self._tabel = (sleutel, tabel)
        return self._tabel[1]

    def _index(self) -> _Index:
        """Lees de koppeltabel en de mappen en wijs aangepaste versies toe aan de originelen."""
        bronmap, doelmap = self.bronmap, self.doelmap
        bestanden = {p.name: p for p in sorted(bronmap.glob("*.prfl"))}
        tabel, regels = None, []
        if self.koppeltabel:
            tabel = self._koppeltabel()
            regels = [(k, self._zoek_profiel(k, bestanden)) for k in tabel.koppelingen]
        gekoppeld = {s for _, s in regels if s}

        zelfde_map = doelmap == bronmap
        if zelfde_map:
            # Originelen zijn de gekoppelde profielen (zonder koppeltabel: alle); de rest kan een versie zijn
            originelen = sorted(gekoppeld) if tabel else list(bestanden)
            kandidaten = {n: p.stat().st_mtime for n, p in bestanden.items() if n not in gekoppeld}
        else:
            originelen = list(bestanden)
            kandidaten = ({p.name: p.stat().st_mtime for p in sorted(doelmap.glob("*.prfl"))}
                          if doelmap.is_dir() else {})
        versies = koppel_versies(originelen, kandidaten, self.achtervoegsel, eigen_naam_overslaan=zelfde_map)

        if zelfde_map:
            # Een bestand dat als versie van een ander profiel is toegewezen, is zelf geen origineel
            toegewezen = {v.naam for vs in versies.values() for v in vs}
            for o in [o for o in versies if o in toegewezen and o not in gekoppeld]:
                del versies[o]
        als_versie = {v.naam for vs in versies.values() for v in vs} if zelfde_map else set()
        return _Index(bestanden, tabel, regels, gekoppeld, versies, als_versie)

    # -- overzicht --
    def overzicht(self) -> dict:
        index = self._index()

        def item(sleutel):
            versies = index.versies.get(sleutel, [])
            pad = self.doelmap / versies[0].naam if versies else index.bestanden[sleutel]
            profiel_id = None
            try:
                profiel = Profiel.from_file(pad)
                status, profiel_id = check_naar_json(profiel.check()), profiel.id
            except Exception as e:  # noqa: BLE001 - een onleesbaar bestand mag het overzicht niet blokkeren
                status = {"ok": False, "code": -1, "naam": "LEESFOUT", "omschrijving": str(e)}
            return {"bestand": sleutel, "bestaat": True, "aangepast": versies[0].naam if versies else None,
                    "versies": [v.als_json() for v in versies], "check": status, "profiel_id": profiel_id}

        vakken = []
        for k, sleutel in index.regels:
            ident = identificeer(k.traject, k.dijkvak, sleutel or k.profiel or None)
            if sleutel:
                gegevens = item(sleutel)
            else:
                reden = ("Bestand niet gevonden in de prfl-map" if k.profiel
                         else "Geen profiel opgegeven in de koppeltabel")
                gegevens = {"bestand": k.profiel or None, "bestaat": False, "reden": reden,
                            "aangepast": None, "versies": []}
            vakken.append({**ident, "info": k.info, "in_koppeltabel": True, **gegevens})

        # Profielen in de map die niet in de koppeltabel staan (zonder koppeltabel: alle profielen)
        for sleutel in index.bestanden:
            if sleutel in index.gekoppeld or sleutel in index.als_versie:
                continue
            vakken.append({**identificeer("", "", sleutel), "info": {}, "in_koppeltabel": False, **item(sleutel)})

        tabel = index.tabel
        tabel_info = None if tabel is None else {
            "kolom_dijkvak": tabel.kolom_dijkvak, "kolom_profiel": tabel.kolom_profiel,
            "kolom_traject": tabel.kolom_traject, "kolommen": tabel.kolommen, "regels": len(tabel.koppelingen)}
        ahn_info = self._koppel_ahn(vakken, index)
        return {"vakken": vakken, "kolommen": tabel.kolommen if tabel else [], "koppeltabel": tabel_info,
                "ahn": ahn_info, "bronmap": str(self.bronmap), "doelmap": str(self.doelmap)}

    # -- AHN --
    def _ahn_bestand(self) -> AhnBestand:
        """De ingelezen shapefile; opnieuw ingelezen als het bestand is gewijzigd."""
        pad = Path(self.ahn_shapefile).resolve()
        sleutel = (str(pad), pad.stat().st_mtime, pad.with_suffix(".dbf").stat().st_mtime
                   if pad.with_suffix(".dbf").exists() else 0)
        if not self._ahn or self._ahn[0] != sleutel:
            logger.info("AHN-shapefile inlezen: %s", pad)
            self._ahn = (sleutel, lees_shapefile(pad))
        return self._ahn[1]

    def _koppel_ahn(self, vakken: list, index: _Index) -> dict | None:
        """Koppel de AHN-lijnen aan de profielen; zet per vak 'ahn' (aantal lijnen) en 'ahn_waarschuwingen'."""
        self._ahn_koppeling = None
        if not self.ahn_shapefile:
            return None
        try:
            ahn = self._ahn_bestand()
            kolommen = kies_kolommen(ahn.velden, self.ahn_kolom_traject or None, self.ahn_kolom_dijkvak or None,
                                     self.ahn_kolom_profiel or None)
        except (ValueError, OSError) as e:
            info = {"bestand": self.ahn_shapefile, "fout": str(e)}
            self._ahn_koppeling = (None, info)
            return info

        def zoek(waarde):
            return self._zoek_profiel(Koppeling(dijkvak="", profiel=waarde), index.bestanden)

        profielen = [v for v in vakken if v["bestaat"]]
        koppeling = koppel(ahn, kolommen, profielen, zoek)
        for v in vakken:
            v["ahn"] = len(koppeling.per_profiel.get(v["bestand"], [])) if v["bestaat"] else 0
            v["ahn_waarschuwingen"] = koppeling.waarschuwingen.get(v["bestand"], [])
        info = {"bestand": str(ahn.pad), "lijnen": len(ahn.lijnen), "kolommen": kolommen, "velden": ahn.velden,
                "niet_gekoppeld": koppeling.niet_gekoppeld, "samenvatting": koppeling.samenvatting(len(ahn.lijnen))}
        self._ahn_koppeling = (koppeling, info)
        return info

    def ahn_lijnen(self, sleutel: str) -> dict:
        """De AHN-lijnen bij een profiel, in profielcoördinaten."""
        if not self.ahn_shapefile:
            return {"lijnen": [], "melding": "Geen AHN-shapefile ingesteld"}
        if self._ahn_koppeling is None:
            self.overzicht()
        koppeling, info = self._ahn_koppeling
        if koppeling is None:
            return {"lijnen": [], "melding": f"AHN-shapefile niet bruikbaar: {info['fout']}", "fout": True}
        ahn = self._ahn_bestand()
        indices = koppeling.per_profiel.get(sleutel, [])
        melding = ""
        if not indices:
            vak = koppeling.profielen.get(sleutel, {})
            vergeleken = ", ".join(f"{kolom} = {vak.get(doel) or 'onbekend'}" if doel != "profiel"
                                   else f"{kolom} = {sleutel}" for doel, kolom in koppeling.kolommen.items() if kolom)
            melding = f"Geen AHN-lijnen gevonden voor dit profiel (gezocht: {vergeleken})."
        return {"lijnen": [ahn.lijnen[i].profiel() for i in indices], "melding": melding,
                "waarschuwingen": koppeling.waarschuwingen.get(sleutel, [])}

    # -- profielen --
    def laad(self, sleutel: str, bron: str = "auto") -> dict:
        """
        Laad een profiel.

        Args:
            sleutel: Bestandsnaam van het origineel in de bronmap
            bron: 'auto' (nieuwste aangepaste versie, anders het origineel), 'origineel',
                of de bestandsnaam van een aangepaste versie
        """
        origineel = self.bronpad(sleutel)
        if not origineel.is_file():
            raise FileNotFoundError(f"Profiel niet gevonden: {sleutel}")
        versies = self._index().versies.get(sleutel, [])
        if bron == "origineel":
            gekozen = None
        elif bron in ("auto", ""):
            gekozen = versies[0] if versies else None
        else:
            gekozen = next((v for v in versies if v.naam == bron), None)
            if gekozen is None:
                raise FileNotFoundError(f"Aangepaste versie niet gevonden: {bron}")
        pad = self.doelmap / gekozen.naam if gekozen else origineel
        profiel = Profiel.from_file(pad)
        data = {
            "bestand": sleutel,
            "geladen": pad.name,
            "is_aangepast": gekozen is not None,
            "versie": gekozen.als_json() if gekozen else None,
            "versies": [v.als_json() for v in versies],
            "aangepast": versies[0].naam if versies else None,
            # opslaan gaat naar de geopende versie, anders naar {naam}{achtervoegsel}.prfl
            "uitvoernaam": gekozen.naam if gekozen else self.standaard_uitvoernaam(sleutel),
            "profiel": profiel_naar_json(profiel),
            "check": check_naar_json(profiel.check()),
        }
        data["origineel"] = profiel_naar_json(Profiel.from_file(origineel)) if gekozen else data["profiel"]
        return data

    def opslaan(self, data: dict) -> dict:
        profiel = json_naar_profiel(data["profiel"])
        versie = ProfielVersion(int(data.get("versie") or self.versie))
        pad = self.uitvoerpad(str(data.get("bestandsnaam") or ""))
        if pad.exists() and not data.get("overschrijven"):
            return {"bestaat": True, "pad": str(pad)}
        pad.parent.mkdir(parents=True, exist_ok=True)
        # Eerst naar een tijdelijk bestand, dan vervangen: een onderbroken schrijfactie laat geen half profiel achter
        tijdelijk = pad.with_name(f".{pad.name}.tmp")
        try:
            profiel.save(tijdelijk, versie)
            os.replace(tijdelijk, pad)
        finally:
            tijdelijk.unlink(missing_ok=True)
        return {"opgeslagen": True, "pad": str(pad), "check": check_naar_json(profiel.check())}


# ── Bestandskeuze via een dialoogvenster op deze computer ─────────────────────
_DIALOOG = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
soort, start = sys.argv[1], sys.argv[2] or None
if soort == "map":
    pad = filedialog.askdirectory(initialdir=start, title="Kies een map")
elif soort == "shp":
    pad = filedialog.askopenfilename(initialdir=start, title="Kies de AHN-shapefile",
        filetypes=[("Shapefile", "*.shp"), ("Alle bestanden", "*.*")])
else:
    pad = filedialog.askopenfilename(initialdir=start, title="Kies de koppeltabel",
        filetypes=[("Koppeltabel", "*.csv *.xlsx *.txt"), ("Alle bestanden", "*.*")])
print(pad or "")
"""


def kies_pad(soort: str, start: str = "") -> str:
    start_map = start if Path(start).is_dir() else str(Path(start).parent) if start else ""
    resultaat = subprocess.run([sys.executable, "-c", _DIALOOG, soort, start_map], check=False,
                               capture_output=True, text=True, timeout=600)
    if resultaat.returncode != 0:
        raise RuntimeError("Dialoogvenster kon niet worden geopend (tkinter niet beschikbaar?)")
    return str(Path(resultaat.stdout.strip())) if resultaat.stdout.strip() else ""


# ── HTTP ───────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    werkruimte: Werkruimte

    def log_message(self, format, *args):
        logger.debug("%s - %s", self.address_string(), format % args)

    def _json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _fout(self, e: Exception, status=HTTPStatus.BAD_REQUEST):
        self._json({"fout": str(e)}, status)

    def _toegestaan(self, post=False) -> bool:
        """
        Weiger verzoeken die niet van de editor zelf komen. Zonder deze controle kan elke website in de
        browser (via een 'simple request' of DNS-rebinding) instellingen wijzigen of profielen wegschrijven.
        """
        poort = self.server.server_address[1]
        hosts = {f"127.0.0.1:{poort}", f"localhost:{poort}"}
        if self.headers.get("Host", "").lower() not in hosts:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin.lower() not in {f"http://{h}" for h in hosts}:
            return False
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        return not post or content_type == "application/json"

    def _body(self) -> dict:
        lengte = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(lengte) or b"{}")

    def _statisch(self, pad: str):
        bestand = (STATIC_MAP / (pad.lstrip("/") or "index.html")).resolve()
        if STATIC_MAP not in bestand.parents or not bestand.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = bestand.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", MIME.get(bestand.suffix, "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        w = self.werkruimte
        if not self._toegestaan():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        try:
            if url.path == "/api/instellingen":
                self._json(w.instellingen())
            elif url.path == "/api/overzicht":
                with w.lock:
                    self._json(w.overzicht())
            elif url.path == "/api/profiel":
                with w.lock:
                    self._json(w.laad(query["bestand"], query.get("bron", "auto")))
            elif url.path == "/api/ahn":
                with w.lock:
                    self._json(w.ahn_lijnen(query["bestand"]))
            elif url.path == "/api/kies":
                self._json({"pad": kies_pad(query.get("soort", "map"), query.get("start", ""))})
            elif url.path.startswith("/api/"):
                self.send_error(HTTPStatus.NOT_FOUND)
            else:
                self._statisch(url.path)
        except FileNotFoundError as e:
            self._fout(e, HTTPStatus.NOT_FOUND)
        except Exception as e:
            logger.exception("Fout bij %s", self.path)
            self._fout(e)

    def do_POST(self):
        url = urlparse(self.path)
        w = self.werkruimte
        if not self._toegestaan(post=True):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))  # anders verbreekt Windows de verbinding
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        try:
            data = self._body()
            if url.path == "/api/instellingen":
                with w.lock:
                    # Alleen wat de gebruiker hier verandert, naar het .ini-bestand: geen opties van de
                    # opdrachtregel en geen paden die bij het starten leeg zijn gemaakt omdat ze niet bestonden
                    gewijzigd = w.pas_aan(data)
                    if w.ini_pad and gewijzigd:
                        bewaar_gewijzigde_instellingen(w.ini_pad, gewijzigd)
                    self._json(w.instellingen())
            elif url.path == "/api/check":
                self._json(check_naar_json(json_naar_profiel(data).check()))
            elif url.path == "/api/tekst":
                profiel = json_naar_profiel(data["profiel"])
                self._json({"tekst": profiel.to_string(ProfielVersion(int(data.get("versie") or w.versie)))})
            elif url.path == "/api/opslaan":
                with w.lock:
                    self._json(w.opslaan(data))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as e:
            logger.exception("Fout bij %s", self.path)
            self._fout(e)


class _Server(ThreadingHTTPServer):
    # Op Windows laat SO_REUSEADDR een tweede proces dezelfde, al gebruikte poort openen;
    # dan zou een tweede editor de verzoeken van de eerste kunnen krijgen.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def maak_server(werkruimte: Werkruimte, host="127.0.0.1", poort=8765) -> ThreadingHTTPServer:
    handler = type("WerkruimteHandler", (Handler,), {"werkruimte": werkruimte})
    for p in range(poort, poort + 20):
        try:
            return _Server((host, p), handler)
        except OSError:
            continue
    raise OSError(f"Geen vrije poort gevonden vanaf {poort}")


# ── Instellingenbestand (.ini) ─────────────────────────────────────────────────
STANDAARD_INI = HOOFDMAP / "profieleditor.ini"
VOORBEELD_INI = HOOFDMAP / "profieleditor.voorbeeld.ini"


def standaard_ini(pad: Path = STANDAARD_INI, voorbeeld: Path = VOORBEELD_INI) -> Path | None:
    """
    Het standaard .ini-bestand. Bestaat het nog niet, dan wordt het gemaakt als kopie van het voorbeeld
    (dat in git staat); het eigen .ini-bestand staat niet in git. None als ook het voorbeeld ontbreekt.
    """
    if not pad.exists() and voorbeeld.exists():
        shutil.copyfile(voorbeeld, pad)
        logger.info("%s aangemaakt uit %s; pas daarin de paden aan, of via Instellingen", pad.name, voorbeeld.name)
    return pad if pad.exists() else None

# sleutel -> (sectie, standaardwaarde)
INI_SLEUTELS = {
    "prfl_map": ("paden", ""),
    "koppeltabel": ("paden", ""),
    "uitvoer_map": ("paden", ""),
    "achtervoegsel": ("opties", "_aangepast"),
    "versie": ("opties", "4"),
    "kolom_dijkvak": ("opties", ""),
    "kolom_profiel": ("opties", ""),
    "kolom_traject": ("opties", ""),
    "ahn_shapefile": ("paden", ""),
    "ahn_kolom_traject": ("opties", ""),
    "ahn_kolom_dijkvak": ("opties", ""),
    "ahn_kolom_profiel": ("opties", ""),
    "poort": ("opties", "8765"),
}
INI_PADEN = ("prfl_map", "koppeltabel", "uitvoer_map", "ahn_shapefile")


def lees_ini(pad) -> dict:
    """
    Lees de instellingen uit een .ini-bestand.

    Relatieve paden gelden ten opzichte van de map van het .ini-bestand. Ontbrekende sleutels
    krijgen hun standaardwaarde. Waarden worden niet geïnterpoleerd, dus % mag in paden voorkomen.
    """
    pad = Path(pad)
    parser = configparser.ConfigParser(interpolation=None)
    with open(pad, encoding="utf-8-sig") as f:
        parser.read_file(f)
    waarden = {}
    for sleutel, (sectie, standaard) in INI_SLEUTELS.items():
        waarde = parser.get(sectie, sleutel, fallback=standaard).strip().strip('"')
        if sleutel in INI_PADEN and waarde and not Path(waarde).is_absolute():
            waarde = str((pad.parent / waarde).resolve())
        waarden[sleutel] = waarde
    return waarden


def schrijf_ini(pad, waarden: dict):
    """
    Werk de opgegeven sleutels bij in het .ini-bestand.

    Het bestand wordt regel voor regel aangepast, zodat commentaar en volgorde behouden blijven.
    Ontbrekende sleutels en secties worden toegevoegd.
    """
    pad = Path(pad)
    data = pad.read_bytes() if pad.exists() else b""
    regeleinde = "\r\n" if b"\r\n" in data else "\n"
    regels = data.decode("utf-8-sig").splitlines()
    open_sleutels = {k: str(v) for k, v in waarden.items() if k in INI_SLEUTELS}

    def regel(sleutel, waarde):
        return f"{sleutel} = {waarde}" if waarde else f"{sleutel} ="

    def voeg_toe_aan_sectie(sectie, einde):
        nieuw = [regel(k, v) for k, v in list(open_sleutels.items()) if INI_SLEUTELS[k][0] == sectie]
        for k in [k for k in open_sleutels if INI_SLEUTELS[k][0] == sectie]:
            del open_sleutels[k]
        regels[einde:einde] = nieuw
        return len(nieuw)

    sectie, i = None, 0
    while i < len(regels):
        tekst = regels[i].strip()
        if tekst.startswith("[") and tekst.endswith("]"):
            # einde van de vorige sectie: ontbrekende sleutels vóór eventuele lege regels invoegen
            einde = i
            while einde > 0 and not regels[einde - 1].strip():
                einde -= 1
            i += voeg_toe_aan_sectie(sectie, einde) if sectie else 0
            sectie = tekst[1:-1].strip().lower()
        elif sectie and "=" in tekst and not tekst.startswith((";", "#")):
            sleutel = tekst.split("=", 1)[0].strip().lower()
            if sleutel in open_sleutels and INI_SLEUTELS[sleutel][0] == sectie:
                regels[i] = regel(sleutel, open_sleutels.pop(sleutel))
        i += 1
    if sectie:
        voeg_toe_aan_sectie(sectie, len(regels))
    for nieuwe_sectie in dict.fromkeys(INI_SLEUTELS[k][0] for k in open_sleutels):
        regels += ["", f"[{nieuwe_sectie}]"]
        voeg_toe_aan_sectie(nieuwe_sectie, len(regels))
    with open(pad, "w", encoding="utf-8", newline="") as f:
        f.write(regeleinde.join(regels).lstrip("\r\n") + regeleinde)


def bewaar_gewijzigde_instellingen(pad, waarden: dict):
    """Schrijf alleen de instellingen die afwijken van het .ini-bestand, zodat relatieve paden blijven staan."""
    huidig = lees_ini(pad) if Path(pad).exists() else {}
    gewijzigd = {k: v for k, v in waarden.items() if k in INI_SLEUTELS and str(v) != huidig.get(k)}
    if gewijzigd:
        schrijf_ini(pad, gewijzigd)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Interactieve profieleditor voor .prfl-bestanden. "
                    "Instellingen komen uit het .ini-bestand; opties op de opdrachtregel gaan daarvoor.")
    parser.add_argument("--ini", default=None,
                        help=f"Instellingenbestand (standaard: {STANDAARD_INI.name} in {HOOFDMAP}; "
                             f"bij de eerste start gemaakt uit {VOORBEELD_INI.name})")
    parser.add_argument("--prfl-map", help="Map met de .prfl-bestanden")
    parser.add_argument("--koppeltabel", help="Koppeltabel dijkvak-profiel (.csv of .xlsx)")
    parser.add_argument("--uitvoer-map", help="Map voor aangepaste profielen (standaard: de prfl-map)")
    parser.add_argument("--achtervoegsel", help="Achtervoegsel van aangepaste profielen (standaard _aangepast)")
    parser.add_argument("--versie", type=int, choices=(3, 4), help="Bestandsversie bij opslaan (standaard 4)")
    parser.add_argument("--kolom-dijkvak", help="Naam van de dijkvak-kolom in de koppeltabel")
    parser.add_argument("--kolom-profiel", help="Naam van de profiel-kolom in de koppeltabel ('-' = geen)")
    parser.add_argument("--kolom-traject", help="Naam van de traject-kolom in de koppeltabel ('-' = geen)")
    parser.add_argument("--ahn-shapefile", help="PolylineZ-shapefile met AHN-dwarsprofielen (bv. cross_lines_ahn.shp)")
    parser.add_argument("--ahn-kolom-traject", help="Traject-kolom in de AHN-shapefile ('-' = geen)")
    parser.add_argument("--ahn-kolom-dijkvak", help="Dijkvak-kolom in de AHN-shapefile ('-' = geen)")
    parser.add_argument("--ahn-kolom-profiel", help="Profielkolom in de AHN-shapefile ('-' = geen)")
    parser.add_argument("--poort", type=int, help="Poort van de server (standaard 8765)")
    parser.add_argument("--geen-browser", action="store_true", help="Open de browser niet automatisch")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ini_pad = Path(args.ini) if args.ini else standaard_ini()
    instellingen = {k: standaard for k, (_, standaard) in INI_SLEUTELS.items()}
    if ini_pad:
        if not ini_pad.exists():
            parser.error(f"Instellingenbestand niet gevonden: {ini_pad}")
        instellingen.update(lees_ini(ini_pad))
        logger.info("Instellingen gelezen uit %s", ini_pad.resolve())
    for sleutel in INI_SLEUTELS:
        waarde = getattr(args, sleutel)
        if waarde is not None:
            instellingen[sleutel] = waarde

    werkruimte = Werkruimte(ini_pad=ini_pad)
    # Een map of koppeltabel die niet bestaat: waarschuwen en leeg laten, zodat de editor de instellingen opent
    for sleutel, controle in (("prfl_map", Path.is_dir), ("koppeltabel", Path.is_file),
                              ("ahn_shapefile", Path.is_file)):
        if instellingen[sleutel] and not controle(Path(instellingen[sleutel])):
            logger.warning("%s bestaat niet: %s", sleutel, instellingen[sleutel])
            instellingen[sleutel] = ""
    try:
        werkruimte.pas_aan(instellingen)
    except ValueError as e:
        parser.error(str(e))
    server = maak_server(werkruimte, poort=int(instellingen["poort"]))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    logger.info("prflcheck %s uit %s", prflcheck.__version__, Path(prflcheck.__file__).parent)
    logger.info("Profieleditor draait op %s  (Ctrl+C om te stoppen)", url)
    if not args.geen_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
