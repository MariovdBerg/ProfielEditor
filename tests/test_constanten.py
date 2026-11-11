"""De editor kleurt profieldelen met een kopie van de grenswaarden uit prflcheck; die moeten gelijk blijven."""

import math
import re
from pathlib import Path

from prflcheck import checks

APP_JS = Path(__file__).resolve().parent.parent / "src" / "static" / "app.js"
VERWACHT = {"TANAMIN", "TANAMAX", "TANAFLW", "TANASTL", "TANABERM", "TANAMINVOORLAND", "DELTAXMINVOORLAND",
            "DELTAXMINDIJK"}


def constanten_uit_app_js() -> dict:
    """De grenswaarden (TANA*, DELTAX*) uit de const-regels van app.js; waarden als 1 / 15 worden uitgerekend."""
    waarden = {}
    for naam, uitdrukking in re.findall(r"\b((?:TANA|DELTAX)\w*)\s*=\s*([\d.]+(?:\s*/\s*[\d.]+)?)",
                                        APP_JS.read_text(encoding="utf-8")):
        teller, _, noemer = uitdrukking.partition("/")
        waarden[naam] = float(teller) / (float(noemer) if noemer else 1.0)
    return waarden


def test_grenswaarden_gelijk_aan_prflcheck():
    js = constanten_uit_app_js()
    assert set(js) == VERWACHT
    verschillen = {naam: (waarde, getattr(checks, naam)) for naam, waarde in js.items()
                   if not math.isclose(waarde, getattr(checks, naam))}
    assert not verschillen, f"app.js wijkt af van prflcheck.checks (app.js, prflcheck): {verschillen}"
