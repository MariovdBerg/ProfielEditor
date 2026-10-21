"""
Identificatie van profielen en hun aangepaste versies
Copyright © 2026 HKV lijn in water B.V.
Licensed under the EUPL
SPDX-License-Identifier: EUPL-1.2

- Traject en dijkvak: eerst uit de koppeltabel; wat daar leeg is, uit de bestandsnaam
  ({traject}_{dijkvak}[_tekst].prfl, alleen als het eerste deel op een traject lijkt, bijvoorbeeld
  34-1, 34a-1 of 35-2); lukt dat ook niet, dan blijft het onbekend (None).
- Aangepaste versies van een origineel {naam}.prfl, gezocht in de uitvoermap:
  1. {naam}{achtervoegsel}.prfl, met het achtervoegsel uit de instellingen;
  2. voor originelen zonder zo'n bestand: elk overgebleven bestand dat begint met {naam}, gevolgd door
     een scheidingsteken (_ - . of spatie) of niets. Alles na {naam} is het achtervoegsel. Past een bestand
     bij meerdere originelen, dan hoort het bij het langste. Is de naam precies gelijk (geen achtervoegsel),
     dan is het een dubbele naam.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

TRAJECT_PATROON = re.compile(r"^(\d+[a-z]?-\d+[a-z]?)_([^_]+)", re.IGNORECASE)
SCHEIDINGSTEKENS = "_-. "


def ontleed_bestandsnaam(bestandsnaam: str) -> tuple[str | None, str | None]:
    """(traject, dijkvak) uit een bestandsnaam als {traject}_{dijkvak}[_tekst].prfl, anders (None, None)."""
    m = TRAJECT_PATROON.match(Path(bestandsnaam).stem)
    return (m.group(1), m.group(2)) if m else (None, None)


def identificeer(traject: str, dijkvak: str, bestandsnaam: str | None) -> dict:
    """
    Traject en dijkvak van een profiel, met per waarde de bron.

    Returns:
        dict met traject, dijkvak (None = onbekend), vak_id ({traject}_{dijkvak} als beide bekend)
        en bron: {"traject": "koppeltabel"|"bestandsnaam"|None, "dijkvak": ...}
    """
    uit_naam = ontleed_bestandsnaam(bestandsnaam) if bestandsnaam else (None, None)
    waarden, bron = {}, {}
    for i, (sleutel, waarde) in enumerate((("traject", traject), ("dijkvak", dijkvak))):
        if waarde:
            waarden[sleutel], bron[sleutel] = waarde, "koppeltabel"
        elif uit_naam[i]:
            waarden[sleutel], bron[sleutel] = uit_naam[i], "bestandsnaam"
        else:
            waarden[sleutel], bron[sleutel] = None, None
    vak_id = f"{waarden['traject']}_{waarden['dijkvak']}" if waarden["traject"] and waarden["dijkvak"] else None
    return {**waarden, "vak_id": vak_id, "bron": bron}


@dataclass
class Versie:
    """Een aangepaste versie van een origineel profiel."""

    naam: str               # bestandsnaam in de uitvoermap
    achtervoegsel: str      # tekst na de naam van het origineel ('' bij een dubbele naam)
    gewijzigd: float = 0.0  # tijdstip van laatste wijziging (epoch)

    @property
    def dubbel(self) -> bool:
        return self.achtervoegsel == ""

    def als_json(self) -> dict:
        return {"naam": self.naam, "achtervoegsel": self.achtervoegsel, "dubbel": self.dubbel,
                "gewijzigd": datetime.fromtimestamp(self.gewijzigd).isoformat(timespec="seconds")
                if self.gewijzigd else None}


def koppel_versies(originelen: list[str], kandidaten: dict[str, float], achtervoegsel: str,
                   eigen_naam_overslaan: bool = False) -> dict[str, list[Versie]]:
    """
    Wijs aangepaste bestanden toe aan originelen.

    Args:
        originelen: Bestandsnamen van de originele profielen
        kandidaten: Bestandsnamen in de uitvoermap -> tijdstip van laatste wijziging
        achtervoegsel: Achtervoegsel uit de instellingen (bijvoorbeeld '_aangepast')
        eigen_naam_overslaan: True als uitvoermap en bronmap dezelfde zijn: een bestand is dan
            niet zijn eigen versie (en er bestaan geen dubbele namen)

    Returns:
        Per origineel de versies, nieuwste eerst (lege lijst als er geen is)
    """
    resultaat = {o: [] for o in originelen}
    vrij = {k.lower(): k for k in kandidaten}

    # Stap 1: {naam}{achtervoegsel}.prfl
    if achtervoegsel:
        for o in originelen:
            naam = f"{Path(o).stem}{achtervoegsel}.prfl".lower()
            if naam in vrij:
                k = vrij.pop(naam)
                resultaat[o].append(Versie(k, achtervoegsel, kandidaten[k]))

    # Stap 2: voor originelen zonder versie, bestanden die met de naam van het origineel beginnen
    open_stammen = sorted(((Path(o).stem.lower(), o) for o in originelen if not resultaat[o]),
                          key=lambda t: len(t[0]), reverse=True)  # langste naam eerst
    for k in sorted(vrij.values()):
        stam = Path(k).stem
        for o_stam, o in open_stammen:
            if eigen_naam_overslaan and stam.lower() == o_stam:
                continue
            if stam.lower() == o_stam or (stam.lower().startswith(o_stam) and stam[len(o_stam)] in SCHEIDINGSTEKENS):
                resultaat[o].append(Versie(k, stam[len(o_stam):], kandidaten[k]))
                break

    for versies in resultaat.values():
        versies.sort(key=lambda v: v.gewijzigd, reverse=True)
    return resultaat
