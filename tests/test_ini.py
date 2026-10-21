from pathlib import Path

from app import (
    INI_PADEN,
    INI_SLEUTELS,
    VOORBEELD_INI,
    bewaar_gewijzigde_instellingen,
    lees_ini,
    schrijf_ini,
    standaard_ini,
)

VOORBEELD = """; commentaar bovenaan
[paden]
; map met profielen
prfl_map = profielen
koppeltabel = C:\\Data met spaties\\koppeling 100%.xlsx

[opties]
versie = 3
"""


def test_lees_ini_relatieve_paden_en_standaarden(tmp_path):
    pad = tmp_path / "instellingen.ini"
    pad.write_text(VOORBEELD, encoding="utf-8")
    waarden = lees_ini(pad)
    assert waarden["prfl_map"] == str((tmp_path / "profielen").resolve())
    assert waarden["koppeltabel"] == "C:\\Data met spaties\\koppeling 100%.xlsx"
    assert waarden["uitvoer_map"] == ""
    assert waarden["versie"] == "3"
    assert waarden["achtervoegsel"] == "_aangepast"


def test_schrijf_ini_behoudt_commentaar_en_vult_aan(tmp_path):
    pad = tmp_path / "instellingen.ini"
    pad.write_text(VOORBEELD, encoding="utf-8")
    schrijf_ini(pad, {"prfl_map": "D:\\nieuw", "uitvoer_map": "D:\\uit", "versie": 4, "ini": "genegeerd"})
    tekst = pad.read_text(encoding="utf-8")
    assert "; commentaar bovenaan" in tekst and "; map met profielen" in tekst
    assert "ini =" not in tekst
    waarden = lees_ini(pad)
    assert (waarden["prfl_map"], waarden["uitvoer_map"], waarden["versie"]) == ("D:\\nieuw", "D:\\uit", "4")
    # de ontbrekende sleutel komt in de sectie [paden], vóór [opties]
    assert tekst.index("uitvoer_map") < tekst.index("[opties]")


def test_schrijf_ini_nieuw_bestand(tmp_path):
    pad = tmp_path / "nieuw.ini"
    schrijf_ini(pad, {"prfl_map": "D:\\p", "achtervoegsel": "_v2"})
    waarden = lees_ini(pad)
    assert waarden["prfl_map"] == "D:\\p" and waarden["achtervoegsel"] == "_v2"


def test_alleen_gewijzigde_waarden_en_regeleinden_behouden(tmp_path):
    pad = tmp_path / "instellingen.ini"
    pad.write_bytes(VOORBEELD.replace("\n", "\r\n").encode("utf-8"))
    waarden = lees_ini(pad)
    waarden["versie"] = 4
    waarden["achtervoegsel"] = ""
    bewaar_gewijzigde_instellingen(pad, waarden)
    data = pad.read_bytes()
    assert b"prfl_map = profielen\r\n" in data      # relatief pad blijft staan
    assert b"uitvoer_map" not in data               # ongewijzigd, dus niet toegevoegd
    assert b"versie = 4\r\n" in data
    assert b"achtervoegsel =\r\n" in data           # lege waarde zonder spatie erachter
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_voorbeeld_ini_bevat_alle_sleutels_en_wijst_naar_testdata():
    tekst = VOORBEELD_INI.read_text(encoding="utf-8")
    assert all(f"{sleutel} =" in tekst for sleutel in INI_SLEUTELS)
    # relatieve paden, zodat het voorbeeld in elke checkout werkt
    waarden = lees_ini(VOORBEELD_INI)
    assert all(Path(waarden[sleutel]).exists() for sleutel in INI_PADEN)


def test_standaard_ini_wordt_uit_voorbeeld_gemaakt(tmp_path):
    pad, voorbeeld = tmp_path / "profieleditor.ini", tmp_path / "profieleditor.voorbeeld.ini"
    assert standaard_ini(pad, voorbeeld) is None
    voorbeeld.write_text(VOORBEELD, encoding="utf-8")
    assert standaard_ini(pad, voorbeeld) == pad and pad.read_text(encoding="utf-8") == VOORBEELD
    pad.write_text("[paden]\n", encoding="utf-8")
    assert standaard_ini(pad, voorbeeld) == pad and pad.read_text(encoding="utf-8") == "[paden]\n"  # niet overschreven
