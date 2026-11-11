"""
Koppeltabel dijkvak <-> profiel
Copyright © 2026 HKV lijn in water B.V.
Licensed under the EUPL
SPDX-License-Identifier: EUPL-1.2

Leest een .csv- of .xlsx-bestand waarin per regel een dijkvak aan een .prfl-bestand
gekoppeld is. Alleen de standaardbibliotheek wordt gebruikt (ook voor .xlsx).

Kolommen worden herkend op naam (hoofdletterongevoelig):
    traject: 'traject', 'traject_id', 'dijktraject', of een kolom met 'traject' in de naam (optioneel)
    dijkvak: 'dijkvak', 'dijkvak_id', 'vak_id', 'vak', of een kolom met 'vak' in de naam
    profiel: 'profiel', 'prfl', 'bestand', 'bestandsnaam', of een kolom met 'prfl'/'profiel' in de naam
Wordt de dijkvak-kolom niet herkend, dan is dat de eerste kolom; de profielkolom is dan de eerste
overige kolom. Zonder profielkolom of met een lege profielcel wordt niet naar een bestand gezocht:
het dijkvak staat dan in het overzicht als 'profiel ontbreekt'. Lege traject- en dijkvakcellen
worden later uit de bestandsnaam gehaald (zie identificatie.py).
Overige kolommen worden als extra informatie per dijkvak bewaard.
"""

from __future__ import annotations

import csv
import io
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

TRAJECT_NAMEN = ("traject", "traject_id", "trajectid", "dijktraject", "dijktraject_id")
DIJKVAK_NAMEN = ("dijkvak", "dijkvak_id", "dijkvakid", "vak_id", "vakid", "vak")
PROFIEL_NAMEN = ("profiel", "prfl", "prfl_bestand", "profielbestand", "bestand", "bestandsnaam", "profiel_id")
GEEN_KOLOM = ("-", "geen")  # opgegeven kolomnaam die betekent: deze kolom niet gebruiken


@dataclass
class Koppeling:
    """Eén regel uit de koppeltabel."""

    dijkvak: str
    profiel: str
    info: dict = field(default_factory=dict)
    traject: str = ""

    @property
    def vak_id(self) -> str:
        """Unieke naam van het dijkvak: {traject}_{dijkvak}, of alleen het dijkvak zonder traject."""
        if self.traject and self.dijkvak:
            return f"{self.traject}_{self.dijkvak}"
        return self.dijkvak or self.traject


@dataclass
class Koppeltabel:
    """De ingelezen koppeltabel."""

    kolom_dijkvak: str
    kolom_profiel: str | None
    kolommen: list
    koppelingen: list
    kolom_traject: str | None = None


def lees_koppeltabel(pad, kolom_dijkvak: str | None = None, kolom_profiel: str | None = None,
                     kolom_traject: str | None = None) -> Koppeltabel:
    """
    Lees een koppeltabel (.csv, .txt of .xlsx).

    Args:
        pad: Pad naar het bestand
        kolom_dijkvak: Naam van de dijkvak-kolom (None = automatisch herkennen)
        kolom_profiel: Naam van de profiel-kolom (None = automatisch herkennen, '-' = niet gebruiken)
        kolom_traject: Naam van de traject-kolom (None = automatisch herkennen, '-' = niet gebruiken)

    Raises:
        ValueError: als het bestand geen bruikbare tabel bevat
    """
    pad = Path(pad)
    if pad.suffix.lower() in (".xlsx", ".xlsm"):
        rijen = _lees_xlsx(pad)
    else:
        rijen = _lees_csv(pad)

    rijen = [[_tekst(c) for c in rij] for rij in rijen]
    rijen = [rij for rij in rijen if any(rij)]
    if len(rijen) < 2:
        raise ValueError(f"{pad.name}: de koppeltabel moet een kopregel en minimaal één regel bevatten")

    kop = [k or f"kolom{i + 1}" for i, k in enumerate(rijen[0])]
    breedte = max(len(rij) for rij in rijen)
    kop += [f"kolom{i + 1}" for i in range(len(kop), breedte)]

    i_traject = _kies_kolom(kop, kolom_traject, TRAJECT_NAMEN, ("traject",), standaard=None)
    i_vak = _kies_kolom(kop, kolom_dijkvak, DIJKVAK_NAMEN, ("vak",),
                        standaard=next(i for i in range(len(kop)) if i != i_traject) if len(kop) > 1 else 0,
                        bezet=(i_traject,))
    overig = [i for i in range(len(kop)) if i not in (i_vak, i_traject)]
    i_prfl = _kies_kolom(kop, kolom_profiel, PROFIEL_NAMEN, ("prfl", "profiel"),
                         standaard=overig[0] if overig else None, bezet=(i_traject, i_vak))
    gekozen = [i for i in (i_traject, i_vak, i_prfl) if i is not None]
    if len(set(gekozen)) < len(gekozen):
        dubbel = next(i for i in gekozen if gekozen.count(i) > 1)
        raise ValueError(f"{pad.name}: kolom '{kop[dubbel]}' is voor meerdere doelen gekozen")
    gebruikt = set(gekozen)

    koppelingen = []
    for rij in rijen[1:]:
        rij = rij + [""] * (len(kop) - len(rij))
        dijkvak = rij[i_vak]
        profiel = rij[i_prfl] if i_prfl is not None else ""
        traject = rij[i_traject] if i_traject is not None else ""
        if not dijkvak and not profiel:
            continue
        info = {kop[i]: rij[i] for i in range(len(kop)) if i not in gebruikt and rij[i]}
        koppelingen.append(Koppeling(dijkvak=dijkvak, profiel=profiel, info=info, traject=traject))

    return Koppeltabel(kolom_dijkvak=kop[i_vak], kolom_profiel=kop[i_prfl] if i_prfl is not None else None,
                       kolommen=kop, koppelingen=koppelingen,
                       kolom_traject=kop[i_traject] if i_traject is not None else None)


def _kies_kolom(kop, opgegeven, namen, deelnamen, standaard, bezet=()):
    """Index van de kolom: de opgegeven naam, anders herkend op naam, anders `standaard` (mag None zijn)."""
    lager = [k.strip().lower() for k in kop]
    if opgegeven and opgegeven.strip().lower() in GEEN_KOLOM:
        return None
    if opgegeven:
        if opgegeven.strip().lower() not in lager:
            raise ValueError(f"Kolom '{opgegeven}' niet gevonden; beschikbare kolommen: {', '.join(kop)}")
        return lager.index(opgegeven.strip().lower())
    vrij = [i for i in range(len(kop)) if i not in bezet]
    for naam in namen:
        for i in vrij:
            if lager[i] == naam:
                return i
    for i in vrij:
        if any(d in lager[i] for d in deelnamen):
            return i
    return standaard


def _tekst(waarde):
    """Celwaarde als tekst; gehele getallen zonder '.0'."""
    if waarde is None:
        return ""
    if isinstance(waarde, float) and waarde.is_integer():
        return str(int(waarde))
    tekst = str(waarde).strip()
    if re.fullmatch(r"-?\d+\.0+", tekst):
        tekst = tekst.split(".")[0]
    return tekst


# ── CSV ────────────────────────────────────────────────────────────────────────
def _lees_csv(pad):
    data = pad.read_bytes()
    try:
        tekst = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        tekst = data.decode("cp1252", errors="replace")
    eerste_regel = tekst.splitlines()[0] if tekst else ""
    scheiding = max(";,\t", key=eerste_regel.count) if eerste_regel else ";"
    return list(csv.reader(io.StringIO(tekst), delimiter=scheiding))


# ── XLSX (alleen het eerste werkblad) ──────────────────────────────────────────
_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def _lees_xlsx(pad):
    try:
        archief = zipfile.ZipFile(pad)
    except zipfile.BadZipFile as e:
        raise ValueError(f"{pad.name} is geen geldig .xlsx-bestand") from e

    with archief:
        gedeeld = []
        if "xl/sharedStrings.xml" in archief.namelist():
            root = ElementTree.fromstring(archief.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                gedeeld.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))

        blad = _eerste_werkblad(archief)
        root = ElementTree.fromstring(archief.read(blad))

    rijen = []
    for rij in root.iter(f"{{{_NS['m']}}}row"):
        cellen = {}
        for c in rij.findall("m:c", _NS):
            kolom = _kolomindex(c.get("r", "")) if c.get("r") else len(cellen)
            cellen[kolom] = _celwaarde(c, gedeeld)
        if cellen:
            rijen.append([cellen.get(i, "") for i in range(max(cellen) + 1)])
    return rijen


def _eerste_werkblad(archief):
    workbook = ElementTree.fromstring(archief.read("xl/workbook.xml"))
    sheet = workbook.find("m:sheets/m:sheet", _NS)
    rel_id = sheet.get(f"{{{_NS['r']}}}id") if sheet is not None else None
    if rel_id and "xl/_rels/workbook.xml.rels" in archief.namelist():
        rels = ElementTree.fromstring(archief.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.findall("rel:Relationship", _NS):
            if rel.get("Id") == rel_id:
                doel = rel.get("Target", "")
                doel = doel.lstrip("/") if doel.startswith("/") else posixpath.normpath(posixpath.join("xl", doel))
                if doel in archief.namelist():
                    return doel
    bladen = sorted(n for n in archief.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
    if not bladen:
        raise ValueError("Het .xlsx-bestand bevat geen werkblad")
    return bladen[0]


def _kolomindex(celref):
    index = 0
    for teken in re.match(r"[A-Z]*", celref.upper()).group():
        index = index * 26 + ord(teken) - ord("A") + 1
    return index - 1


def _celwaarde(c, gedeeld):
    soort = c.get("t", "n")
    if soort == "inlineStr":
        return "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
    v = c.find("m:v", _NS)
    if v is None or v.text is None:
        return ""
    if soort == "s":
        return gedeeld[int(v.text)]
    if soort == "n":
        try:
            return float(v.text)
        except ValueError:
            return v.text
    return v.text
