"""
AHN-dwarsprofielen uit een shapefile

Leest een PolylineZ-shapefile (bijvoorbeeld cross_lines_ahn.shp) met de .dbf ernaast, en koppelt
de lijnen aan profielen. Alleen de standaardbibliotheek wordt gebruikt.

Koppelen, per lijn:
  1. Heeft de shapefile een profielkolom met een waarde die een bekend profiel aanwijst, dan hoort
     de lijn bij dat profiel. Wijken traject of dijkvak van de lijn af van die van het profiel, dan
     wordt dat als waarschuwing bij het profiel gemeld (de shapefile wordt gevolgd).
  2. Anders: traject en dijkvak van de lijn moeten exact gelijk zijn aan die van het profiel
     (zonder trajectkolom alleen het dijkvak).
  Lijnen die nergens bij passen, worden geteld en met voorbeelden gemeld.

Omzetten naar profielcoördinaten (zoals in prfl_editor_v28.ipynb): x is de afstand langs de lijn
min de halve lijnlengte (x = 0 in het midden van de lijn), z is de AHN-hoogte. Punten zonder
hoogte (z <= -9990, bijvoorbeeld -99999) worden weggelaten.
"""

from __future__ import annotations

import math
import struct
from array import array
from dataclasses import dataclass, field
from pathlib import Path

from koppeling import DIJKVAK_NAMEN, PROFIEL_NAMEN, TRAJECT_NAMEN, _kies_kolom, _tekst

GEEN_HOOGTE = -9990.0
Z_TYPEN = {13: "PolylineZ", 15: "PolygonZ"}


@dataclass
class AhnLijn:
    attributen: dict
    xy: array    # x0, y0, x1, y1, ... (RD)
    z: array
    delen: tuple = (0,)  # index van het eerste punt van elk deel (multipart)

    def profiel(self) -> list[list[float] | None]:
        """
        [[x, z], ...] met x = afstand langs de lijn min de halve lengte; punten zonder hoogte weggelaten.
        Tussen de delen van een multipart-lijn staat None, zodat het gat niet wordt overbrugd.
        """
        afstanden, totaal = [0.0], 0.0
        for i in range(1, len(self.z)):
            totaal += math.hypot(self.xy[2 * i] - self.xy[2 * i - 2], self.xy[2 * i + 1] - self.xy[2 * i - 1])
            afstanden.append(totaal)
        half = totaal / 2
        starts = set(self.delen[1:])
        punten = []
        for i, (a, z) in enumerate(zip(afstanden, self.z)):
            if i in starts and punten and punten[-1] is not None:
                punten.append(None)
            if z > GEEN_HOOGTE:
                punten.append([round(a - half, 3), round(z, 3)])
        return punten


@dataclass
class AhnBestand:
    pad: Path
    velden: list
    lijnen: list = field(default_factory=list)


def lees_shapefile(pad) -> AhnBestand:
    """Lees een PolylineZ-shapefile en de bijbehorende .dbf (codering uit de .cpg, anders latin-1)."""
    pad = Path(pad)
    dbf = pad.with_suffix(".dbf")
    if not dbf.is_file():
        raise ValueError(f"De .dbf bij {pad.name} ontbreekt")
    data = pad.read_bytes()
    if len(data) < 100:
        raise ValueError(f"{pad.name} is geen geldige shapefile")
    soort = struct.unpack_from("<i", data, 32)[0]
    if soort not in Z_TYPEN:
        raise ValueError(f"{pad.name} heeft geen hoogtes (shapetype {soort}); gebruik een PolylineZ-shapefile "
                         f"zoals cross_lines_ahn.shp")

    vormen = []
    positie = 100
    while positie + 8 <= len(data):
        lengte = struct.unpack_from(">i", data, positie + 4)[0] * 2
        inhoud = positie + 8
        positie = inhoud + lengte
        if struct.unpack_from("<i", data, inhoud)[0] not in Z_TYPEN:  # bijvoorbeeld een lege vorm
            vormen.append((array("d"), array("d"), (0,)))
            continue
        delen, punten = struct.unpack_from("<2i", data, inhoud + 36)
        starts = struct.unpack_from(f"<{delen}i", data, inhoud + 44)
        start_xy = inhoud + 44 + 4 * delen
        xy = array("d", struct.unpack_from(f"<{2 * punten}d", data, start_xy))
        z = array("d", struct.unpack_from(f"<{punten}d", data, start_xy + 16 * punten + 16))
        vormen.append((xy, z, starts or (0,)))

    velden, records = _lees_dbf(dbf)
    if len(records) != len(vormen):
        raise ValueError(f"{pad.name}: {len(vormen)} vormen maar {len(records)} regels in de .dbf")
    # Verwijderde regels in de .dbf (None) horen bij vormen die niet meer meetellen
    return AhnBestand(pad, velden, [AhnLijn(r, xy, z, starts)
                                    for r, (xy, z, starts) in zip(records, vormen) if r is not None])


def _lees_dbf(pad: Path):
    cpg = pad.with_suffix(".cpg")
    codering = "latin-1"
    if cpg.is_file():
        codering = {"iso-8859-1": "latin-1", "1252": "cp1252", "ansi 1252": "cp1252"}.get(
            cpg.read_text(errors="ignore").strip().lower(), cpg.read_text(errors="ignore").strip() or "latin-1")
    data = pad.read_bytes()
    aantal = struct.unpack_from("<I", data, 4)[0]
    kop, regel = struct.unpack_from("<2H", data, 8)
    velden, positie = [], 32
    while data[positie] != 0x0D:
        naam = data[positie:positie + 11].split(b"\0")[0].decode("latin-1")
        velden.append((naam, data[positie + 16]))
        positie += 32
    records = []
    for i in range(aantal):
        start = kop + i * regel
        if data[start:start + 1] == b"*":  # verwijderd-vlag
            records.append(None)
            continue
        start += 1
        record = {}
        for naam, lengte in velden:
            try:
                record[naam] = _tekst(data[start:start + lengte].decode(codering, errors="replace").strip())
            except LookupError:
                record[naam] = _tekst(data[start:start + lengte].decode("latin-1").strip())
            start += lengte
        records.append(record)
    return [naam for naam, _ in velden], records


# ── Koppelen aan profielen ─────────────────────────────────────────────────────
def kies_kolommen(velden, traject=None, dijkvak=None, profiel=None) -> dict:
    """Kolommen voor traject, dijkvak en profiel: opgegeven naam, anders herkend op naam, anders None."""
    i_t = _kies_kolom(velden, traject, TRAJECT_NAMEN, ("traject",), standaard=None)
    i_d = _kies_kolom(velden, dijkvak, DIJKVAK_NAMEN, ("vak",), standaard=None, bezet=(i_t,))
    i_p = _kies_kolom(velden, profiel, PROFIEL_NAMEN, ("prfl", "profiel"), standaard=None, bezet=(i_t, i_d))
    kolommen = {k: velden[i] if i is not None else None for k, i in (("traject", i_t), ("dijkvak", i_d),
                                                                      ("profiel", i_p))}
    if not kolommen["dijkvak"] and not kolommen["profiel"]:
        raise ValueError("Geen dijkvak- of profielkolom gevonden in de shapefile; kolommen: " + ", ".join(velden))
    return kolommen


@dataclass
class AhnKoppeling:
    kolommen: dict
    per_profiel: dict      # bestand -> [index van de lijn]
    waarschuwingen: dict   # bestand -> [tekst]
    niet_gekoppeld: int
    voorbeelden: list      # voorbeelden van niet-gekoppelde (traject, dijkvak, profiel)
    profiel_onbekend: int  # lijnen waarvan de profielwaarde geen bekend profiel is
    profielen: dict = field(default_factory=dict)  # bestand -> profiel (traject, dijkvak) zoals gekoppeld

    def samenvatting(self, totaal: int) -> str:
        gekoppeld = totaal - self.niet_gekoppeld
        vergelijk = [f"{kolom} = {doel}" for doel, kolom in self.kolommen.items() if kolom]
        tekst = f"{gekoppeld} van {totaal} AHN-lijnen gekoppeld (vergeleken: {', '.join(vergelijk)})."
        if self.niet_gekoppeld:
            bv = "; ".join("/".join(w or "–" for w in v) for v in self.voorbeelden)
            tekst += f" Niet gekoppeld: {self.niet_gekoppeld}, bijvoorbeeld {bv}."
        if self.profiel_onbekend:
            tekst += f" Bij {self.profiel_onbekend} lijnen wijst de profielkolom geen bekend profiel aan."
        return tekst


def koppel(ahn: AhnBestand, kolommen: dict, profielen: list[dict], zoek_profiel) -> AhnKoppeling:
    """
    Koppel de AHN-lijnen aan profielen.

    Args:
        ahn: De ingelezen shapefile
        kolommen: Uitkomst van kies_kolommen
        profielen: Profielen uit het overzicht: dicts met bestand, traject en dijkvak
        zoek_profiel: Functie die een profielwaarde uit de shapefile omzet naar een bestand (of None)
    """
    per_vak = {}
    for p in profielen:
        if p.get("dijkvak"):
            sleutel = (p.get("traject") or "", p["dijkvak"]) if kolommen["traject"] else p["dijkvak"]
            per_vak.setdefault(sleutel, []).append(p["bestand"])
    per_bestand = {p["bestand"]: p for p in profielen}

    per_profiel, waarschuwingen, conflicten = {}, {}, {}
    niet_gekoppeld, profiel_onbekend, voorbeelden = 0, 0, []
    for i, lijn in enumerate(ahn.lijnen):
        a = lijn.attributen
        traject = a.get(kolommen["traject"], "") if kolommen["traject"] else ""
        dijkvak = a.get(kolommen["dijkvak"], "") if kolommen["dijkvak"] else ""
        profiel = a.get(kolommen["profiel"], "") if kolommen["profiel"] else ""

        doelen = []
        if profiel:
            bestand = zoek_profiel(profiel)
            if bestand in per_bestand:
                doelen = [bestand]
                p = per_bestand[bestand]
                anders = [(naam, waarde, p.get(naam)) for naam, waarde in (("traject", traject), ("dijkvak", dijkvak))
                          if waarde and waarde != (p.get(naam) or "")]
                if anders:
                    tekst = ", ".join(f"{naam} {waarde} (koppeltabel: {eigen or 'onbekend'})"
                                      for naam, waarde, eigen in anders)
                    conflicten.setdefault(bestand, {}).setdefault(tekst, 0)
                    conflicten[bestand][tekst] += 1
            else:
                profiel_onbekend += 1
        if not doelen and dijkvak:
            doelen = per_vak.get((traject, dijkvak) if kolommen["traject"] else dijkvak, [])
        if not doelen:
            niet_gekoppeld += 1
            voorbeeld = (traject, dijkvak, profiel)
            if len(voorbeelden) < 3 and voorbeeld not in voorbeelden:
                voorbeelden.append(voorbeeld)
            continue
        for bestand in doelen:
            per_profiel.setdefault(bestand, []).append(i)

    for bestand, teksten in conflicten.items():
        waarschuwingen[bestand] = [f"AHN-koppeling wijkt af van koppeltabel: {n} lijn(en) met dit profiel hebben {t}"
                                   for t, n in teksten.items()]
    return AhnKoppeling(kolommen, per_profiel, waarschuwingen, niet_gekoppeld, voorbeelden, profiel_onbekend,
                        per_bestand)
