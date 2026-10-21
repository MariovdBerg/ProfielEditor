import json
import math
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from prflcheck import Profiel, ProfielPunt

from app import Werkruimte, json_naar_profiel, maak_server, profiel_naar_json


def maak_profiel(pad, voorland=True, id="P1"):
    punten = [ProfielPunt(-50, 1.0, 1), ProfielPunt(0, 2.0, 1), ProfielPunt(6, 3.0, 1), ProfielPunt(26, 3.8, 1),
              ProfielPunt(32, 5.5, 1), ProfielPunt(37, 8.0, 1)]
    if not voorland:
        punten = punten[1:]
    Profiel.from_punten(punten, voorland=2 if voorland else 0, id=id, richting=90.0, kruinhoogte=8.5,
                        damhoogte=0.0, memo="test").save(pad)


@pytest.fixture
def werkruimte(tmp_path):
    bron = tmp_path / "prfl"
    bron.mkdir()
    maak_profiel(bron / "34-1_1.prfl")
    maak_profiel(bron / "34-1_2.prfl", voorland=False)
    (tmp_path / "k.csv").write_text("dijkvak;profiel;km\nA;34-1_1.prfl;1\nB;34-1_2;2\nC;weg.prfl;3\n", encoding="utf-8")
    return Werkruimte(prfl_map=str(bron), koppeltabel=str(tmp_path / "k.csv"), uitvoer_map=str(tmp_path / "uit"))


def test_json_heen_en_weer():
    profiel = Profiel.from_punten([ProfielPunt(-50, 1, 1), ProfielPunt(0, 2, 1), ProfielPunt(5, 4, 1)], voorland=2,
                                  id="X", kruinhoogte=5.0)
    data = profiel_naar_json(profiel)
    assert data["voorland"] == 2 and len(data["punten"]) == 3
    assert data["richting"] is None  # NaN wordt null
    json.dumps(data, allow_nan=False)
    terug = json_naar_profiel(data)
    assert terug.voorland_punten == profiel.voorland_punten
    assert terug.dijk_punten == profiel.dijk_punten
    assert math.isnan(terug.richting)


def test_overzicht(werkruimte):
    vakken = werkruimte.overzicht()["vakken"]
    assert [(v["dijkvak"], v["bestand"], v["bestaat"]) for v in vakken] == [
        ("A", "34-1_1.prfl", True), ("B", "34-1_2.prfl", True), ("C", "weg.prfl", False)]
    assert all(v["check"]["ok"] for v in vakken[:2])
    assert vakken[0]["info"] == {"km": "1"}


def test_laden_opslaan_en_aangepaste_versie(werkruimte):
    data = werkruimte.laad("34-1_1.prfl")
    assert not data["is_aangepast"] and data["uitvoernaam"] == "34-1_1_aangepast.prfl"
    profiel = data["profiel"]
    profiel["punten"][-1][1] = 9.0
    profiel["kruinhoogte"] = 9.5

    res = werkruimte.opslaan({"profiel": profiel, "bestandsnaam": data["uitvoernaam"], "versie": 3})
    assert res["opgeslagen"] and res["check"]["ok"]
    assert werkruimte.opslaan({"profiel": profiel, "bestandsnaam": data["uitvoernaam"]})["bestaat"]

    opnieuw = werkruimte.laad("34-1_1.prfl")
    assert opnieuw["is_aangepast"] and opnieuw["profiel"]["punten"][-1][1] == 9.0
    assert opnieuw["origineel"]["punten"][-1][1] == 8.0
    assert werkruimte.laad("34-1_1.prfl", bron="origineel")["profiel"]["kruinhoogte"] == 8.5
    assert werkruimte.overzicht()["vakken"][0]["aangepast"] == "34-1_1_aangepast.prfl"


def test_paden_buiten_map_geweigerd(werkruimte):
    with pytest.raises(ValueError):
        werkruimte.laad("../k.csv")
    with pytest.raises(ValueError):
        werkruimte.opslaan({"profiel": {"punten": []}, "bestandsnaam": "../x.prfl"})


def test_zonder_koppeltabel_uitvoer_in_zelfde_map(werkruimte, tmp_path):
    werkruimte.koppeltabel = ""
    werkruimte.uitvoer_map = ""
    data = werkruimte.laad("34-1_2.prfl")
    werkruimte.opslaan({"profiel": data["profiel"], "bestandsnaam": data["uitvoernaam"]})
    # Het aangepaste bestand staat in dezelfde map, maar verschijnt niet als apart profiel
    assert [v["bestand"] for v in werkruimte.overzicht()["vakken"]] == ["34-1_1.prfl", "34-1_2.prfl"]


def test_http_api(werkruimte):
    server = maak_server(werkruimte, poort=18765)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    basis = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        def post(pad, body):
            verzoek = urllib.request.Request(basis + pad, json.dumps(body).encode(), {"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(verzoek))

        profiel = json.load(urllib.request.urlopen(f"{basis}/api/profiel?bestand=34-1_1.prfl"))["profiel"]
        assert post("/api/check", profiel)["ok"]
        profiel["punten"][3][1] = 2.0  # dijk loopt niet meer op
        assert post("/api/check", profiel)["naam"] == "ERROR112"
        assert post("/api/tekst", {"profiel": profiel, "versie": 4})["tekst"].startswith("VERSIE 4.0")
        assert urllib.request.urlopen(basis + "/").read().startswith(b"<!doctype html>")
    finally:
        server.shutdown()
        server.server_close()


def test_identificatie_en_versies(tmp_path):
    bron, uit = tmp_path / "prfl", tmp_path / "uit"
    bron.mkdir()
    uit.mkdir()
    for naam in ["34-1_6.prfl", "35-2_6.prfl", "35-2_15.prfl", "dijk_noord.prfl", "34-1_7.prfl", "36-1_1.prfl"]:
        maak_profiel(bron / naam, id=Path(naam).stem)
    for naam in ["34-1_6_aangepast.prfl", "35-2_6_damwand.prfl", "35-2_6_v2.prfl", "35-2_15.prfl",
                 "dijk_noord-x.prfl"]:
        maak_profiel(uit / naam)
    os.utime(uit / "35-2_6_v2.prfl", (2_000_000_000, 2_000_000_000))  # nieuwste versie
    (tmp_path / "k.csv").write_text(
        "traject;dijkvak;profiel\n"
        "34-1;6;34-1_6.prfl\n"          # alles uit de koppeltabel
        ";6;35-2_6.prfl\n"              # traject uit de bestandsnaam
        "35-2;;35-2_15.prfl\n"          # dijkvak uit de bestandsnaam
        ";;dijk_noord.prfl\n"           # bestandsnaam lijkt niet op {traject}_{dijkvak}: onbekend
        "34-1;7;\n"                     # geen profiel opgegeven: ontbreekt (niet raden)
        "34-1;8;bestaat_niet.prfl\n",
        encoding="utf-8")
    w = Werkruimte(prfl_map=str(bron), koppeltabel=str(tmp_path / "k.csv"), uitvoer_map=str(uit))
    vakken = {(v["bestand"] or f"regel{i}"): v for i, v in enumerate(w.overzicht()["vakken"])}

    v = vakken["34-1_6.prfl"]
    assert (v["vak_id"], v["bron"]) == ("34-1_6", {"traject": "koppeltabel", "dijkvak": "koppeltabel"})
    assert [x["naam"] for x in v["versies"]] == ["34-1_6_aangepast.prfl"]

    v = vakken["35-2_6.prfl"]
    assert (v["traject"], v["dijkvak"], v["bron"]["traject"]) == ("35-2", "6", "bestandsnaam")
    assert [(x["naam"], x["achtervoegsel"]) for x in v["versies"]] == [
        ("35-2_6_v2.prfl", "_v2"), ("35-2_6_damwand.prfl", "_damwand")]
    assert v["aangepast"] == "35-2_6_v2.prfl"

    v = vakken["35-2_15.prfl"]
    assert (v["dijkvak"], v["bron"]["dijkvak"]) == ("15", "bestandsnaam")
    assert v["versies"][0]["dubbel"] and v["versies"][0]["achtervoegsel"] == ""

    v = vakken["dijk_noord.prfl"]
    assert (v["traject"], v["dijkvak"], v["vak_id"]) == (None, None, None)
    assert v["versies"][0]["achtervoegsel"] == "-x"

    assert vakken["regel4"]["bestaat"] is False and "Geen profiel" in vakken["regel4"]["reden"]
    assert vakken["bestaat_niet.prfl"]["reden"] == "Bestand niet gevonden in de prfl-map"

    v = vakken["34-1_7.prfl"]  # niet in de koppeltabel (regel had geen profiel): uit de bestandsnaam
    assert (v["in_koppeltabel"], v["vak_id"], v["bron"]["traject"]) == (False, "34-1_7", "bestandsnaam")

    # laden: standaard de nieuwste versie, op naam een andere, en opslaan gaat naar de geopende versie
    data = w.laad("35-2_6.prfl")
    assert (data["geladen"], data["uitvoernaam"]) == ("35-2_6_v2.prfl", "35-2_6_v2.prfl")
    data = w.laad("35-2_6.prfl", bron="35-2_6_damwand.prfl")
    assert data["uitvoernaam"] == "35-2_6_damwand.prfl"
    assert w.laad("36-1_1.prfl")["uitvoernaam"] == "36-1_1_aangepast.prfl"
    with pytest.raises(FileNotFoundError):
        w.laad("35-2_6.prfl", bron="onbekend.prfl")


def test_versies_in_dezelfde_map(tmp_path):
    bron = tmp_path / "prfl"
    bron.mkdir()
    for naam in ["34-1_6.prfl", "34-1_6_damwand.prfl", "34-1_7.prfl", "34-1_7_aangepast.prfl", "34-1_8.prfl"]:
        maak_profiel(bron / naam)
    w = Werkruimte(prfl_map=str(bron))
    vakken = w.overzicht()["vakken"]
    assert [(v["bestand"], v["aangepast"]) for v in vakken] == [
        ("34-1_6.prfl", "34-1_6_damwand.prfl"), ("34-1_7.prfl", "34-1_7_aangepast.prfl"), ("34-1_8.prfl", None)]
    assert not any(x["dubbel"] for v in vakken for x in v["versies"])


def test_bezette_poort_geeft_volgende_poort(werkruimte):
    eerste = maak_server(werkruimte, poort=18800)
    tweede = maak_server(werkruimte, poort=eerste.server_address[1])
    try:
        assert tweede.server_address[1] != eerste.server_address[1]
    finally:
        eerste.server_close()
        tweede.server_close()


def test_pas_aan_geeft_alleen_wijzigingen(werkruimte):
    instellingen = werkruimte.instellingen()
    assert werkruimte.pas_aan(instellingen) == {}
    assert werkruimte.pas_aan({**instellingen, "versie": 3, "achtervoegsel": "_v2"}) == {"versie": 3,
                                                                                        "achtervoegsel": "_v2"}


def test_instellingen_bewaren_wist_geen_paden_uit_ini(werkruimte, tmp_path):
    # Bij het starten is ahn_shapefile leeggemaakt (het bestand bestond niet, bijvoorbeeld P: niet gekoppeld);
    # wijzigen van een andere instelling mag dat pad niet uit het .ini-bestand wissen.
    ini = tmp_path / "instellingen.ini"
    ini.write_text("[paden]\nahn_shapefile = P:/ahn/lijnen.shp\n\n[opties]\nversie = 4\n", encoding="utf-8")
    werkruimte.ini_pad = ini
    server = maak_server(werkruimte, poort=18810)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        basis = f"http://127.0.0.1:{server.server_address[1]}"
        body = json.dumps({**werkruimte.instellingen(), "versie": 3}).encode()
        urllib.request.urlopen(urllib.request.Request(basis + "/api/instellingen", body,
                                                      {"Content-Type": "application/json"}))
    finally:
        server.shutdown()
        server.server_close()
    tekst = ini.read_text(encoding="utf-8")
    assert "ahn_shapefile = P:/ahn/lijnen.shp" in tekst and "versie = 3" in tekst
    assert "prfl_map" not in tekst


@pytest.mark.parametrize("headers", [
    {"Host": "evil.example:18820"},                                           # DNS-rebinding
    {"Origin": "http://evil.example"},                                        # andere website
    {"Content-Type": "text/plain"},                                           # 'simple request' zonder preflight
])
def test_vreemde_verzoeken_geweigerd(werkruimte, headers):
    server = maak_server(werkruimte, poort=18820)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        poort = server.server_address[1]
        headers = {"Content-Type": "application/json", **headers}
        if "Host" in headers:
            headers["Host"] = headers["Host"].replace("18820", str(poort))
        verzoek = urllib.request.Request(f"http://127.0.0.1:{poort}/api/instellingen", b'{"versie": 3}', headers)
        with pytest.raises(urllib.error.HTTPError) as fout:
            urllib.request.urlopen(verzoek)
        assert fout.value.code == 403
        assert werkruimte.versie == 4
        # de editor zelf (localhost, eigen Origin) mag wel
        eigen = urllib.request.Request(f"http://127.0.0.1:{poort}/api/instellingen", b'{"versie": 3}',
                                       {"Content-Type": "application/json", "Host": f"localhost:{poort}",
                                        "Origin": f"http://localhost:{poort}"})
        urllib.request.urlopen(eigen)
        assert werkruimte.versie == 3
    finally:
        server.shutdown()
        server.server_close()


def test_opslaan_laat_geen_tijdelijk_bestand_achter(werkruimte):
    data = werkruimte.laad("34-1_1.prfl")
    werkruimte.opslaan({"profiel": data["profiel"], "bestandsnaam": "34-1_1_aangepast.prfl"})
    werkruimte.opslaan({"profiel": data["profiel"], "bestandsnaam": "34-1_1_aangepast.prfl", "overschrijven": True})
    assert [p.name for p in werkruimte.doelmap.iterdir()] == ["34-1_1_aangepast.prfl"]


def test_koppeltabel_wordt_hergebruikt_tot_die_verandert(werkruimte):
    eerste = werkruimte._koppeltabel()
    assert werkruimte._koppeltabel() is eerste
    pad = Path(werkruimte.koppeltabel)
    pad.write_text(pad.read_text(encoding="utf-8") + "D;34-1_2.prfl;4\n", encoding="utf-8")
    os.utime(pad, ns=(pad.stat().st_atime_ns, pad.stat().st_mtime_ns + 10**9))
    assert len(werkruimte._koppeltabel().koppelingen) == len(eerste.koppelingen) + 1
