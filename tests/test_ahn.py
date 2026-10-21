import struct
from pathlib import Path

import pytest

from ahn import kies_kolommen, koppel, lees_shapefile

TEST_SHAPE = Path(__file__).parent / "test_shapefiles" / "cross_lines_ahn.shp"


def schrijf_shapefile(pad, lijnen, velden, soort=13):
    """Minimale PolylineZ-shapefile: lijnen = [([(x, y, z), ...], {veld: waarde}[, (start deel 1, ...)])]."""
    records = b""
    for nr, (punten, _, *delen) in enumerate(lijnen, start=1):
        n = len(punten)
        xs, ys, zs = zip(*punten)
        starts = delen[0] if delen else (0,)
        inhoud = struct.pack("<i4d2i", soort, min(xs), min(ys), max(xs), max(ys), len(starts), n)
        inhoud += struct.pack(f"<{len(starts)}i", *starts)
        inhoud += b"".join(struct.pack("<2d", x, y) for x, y, _ in punten)
        inhoud += struct.pack("<2d", min(zs), max(zs)) + b"".join(struct.pack("<d", z) for z in zs)
        records += struct.pack(">2i", nr, len(inhoud) // 2) + inhoud
    kop = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(records)) // 2) + struct.pack("<2i", 1000, soort)
    kop += struct.pack("<8d", *([0.0] * 8))
    Path(pad).write_bytes(kop + records)

    breedte = 20
    dbf_kop = struct.pack("<4BIHH20x", 3, 26, 1, 1, len(lijnen), 32 + 32 * len(velden) + 1, 1 + breedte * len(velden))
    for veld in velden:
        dbf_kop += veld.encode("latin-1").ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([breedte, 0]) + b"\0" * 14
    dbf_kop += b"\r"
    regels = b"".join(b" " + b"".join(str(a.get(v, "")).encode("latin-1").ljust(breedte) for v in velden)
                      for _, a, *_ in lijnen)
    Path(pad).with_suffix(".dbf").write_bytes(dbf_kop + regels + b"\x1a")


def lijn(y, z_waarden, **attributen):
    """Lijn langs de x-as (RD-x 0..40 m), op RD-y = y."""
    return [(i * 10.0, y, z) for i, z in enumerate(z_waarden)], attributen


@pytest.fixture
def shapefile(tmp_path):
    pad = tmp_path / "ahn.shp"
    schrijf_shapefile(pad, [
        lijn(0, [1, 2, -99999, 4, 5], TRAJECT="34-1", vak_id="145"),
        lijn(5, [1, 1, 1, 1, 1], TRAJECT="34-1", vak_id="145", profiel="35-2_6.prfl"),   # profiel wint
        lijn(9, [2, 2, 2, 2, 2], TRAJECT="35-2", vak_id="145"),
        lijn(9, [3, 3, 3, 3, 3], TRAJECT="34-1", vak_id="34-1_146"),                    # niet exact: geen match
        lijn(9, [3, 3, 3, 3, 3], TRAJECT="34-1", vak_id="147", profiel="onbekend.prfl"),
    ], ["TRAJECT", "vak_id", "profiel"])
    return pad


PROFIELEN = [
    {"bestand": "34-1_145.prfl", "traject": "34-1", "dijkvak": "145"},
    {"bestand": "35-2_145.prfl", "traject": "35-2", "dijkvak": "145"},
    {"bestand": "35-2_6.prfl", "traject": "35-2", "dijkvak": "6"},
    {"bestand": "34-1_147.prfl", "traject": "34-1", "dijkvak": "147"},
]


def zoek(waarde):
    return waarde if waarde in {p["bestand"] for p in PROFIELEN} else None


def test_lezen_en_omzetten(shapefile):
    ahn = lees_shapefile(shapefile)
    assert ahn.velden == ["TRAJECT", "vak_id", "profiel"] and len(ahn.lijnen) == 5
    assert ahn.lijnen[0].attributen == {"TRAJECT": "34-1", "vak_id": "145", "profiel": ""}
    # x = afstand langs de lijn min de halve lengte; het punt zonder hoogte valt weg
    assert ahn.lijnen[0].profiel() == [[-20.0, 1.0], [-10.0, 2.0], [10.0, 4.0], [20.0, 5.0]]


def test_multipart_en_verwijderde_regels(tmp_path):
    pad = tmp_path / "multi.shp"
    punten = [(i * 10.0, 0, z) for i, z in enumerate([1, 2, 3, 4, 5])]
    schrijf_shapefile(pad, [
        (punten, {"vak_id": "1"}, (0, 3)),   # twee delen: punten 0-2 en 3-4
        lijn(0, [1, 1], vak_id="2"),
        lijn(0, [2, 2], vak_id="3"),
    ], ["vak_id"])
    dbf = pad.with_suffix(".dbf")
    data = bytearray(dbf.read_bytes())
    kop, regel = struct.unpack_from("<2H", data, 8)
    data[kop + regel] = ord("*")  # tweede regel verwijderd
    dbf.write_bytes(bytes(data))

    ahn = lees_shapefile(pad)
    assert [lijn.attributen["vak_id"] for lijn in ahn.lijnen] == ["1", "3"]
    assert ahn.lijnen[1].profiel() == [[-5.0, 2.0], [5.0, 2.0]]
    # tussen de delen staat None, zodat de editor het gat niet overbrugt
    assert ahn.lijnen[0].profiel() == [[-20.0, 1.0], [-10.0, 2.0], [0.0, 3.0], None, [10.0, 4.0], [20.0, 5.0]]


def test_koppelen_exact_en_profiel_wint(shapefile):
    ahn = lees_shapefile(shapefile)
    kolommen = kies_kolommen(ahn.velden)
    assert kolommen == {"traject": "TRAJECT", "dijkvak": "vak_id", "profiel": "profiel"}
    k = koppel(ahn, kolommen, PROFIELEN, zoek)
    assert k.per_profiel == {"34-1_145.prfl": [0], "35-2_6.prfl": [1], "35-2_145.prfl": [2], "34-1_147.prfl": [4]}
    assert k.waarschuwingen["35-2_6.prfl"] == [
        ("AHN-koppeling wijkt af van koppeltabel: 1 lijn(en) met dit profiel hebben "
         "traject 34-1 (koppeltabel: 35-2), dijkvak 145 (koppeltabel: 6)")]
    assert (k.niet_gekoppeld, k.voorbeelden, k.profiel_onbekend) == (1, [("34-1", "34-1_146", "")], 1)
    assert "4 van 5 AHN-lijnen gekoppeld" in k.samenvatting(5)


def test_zonder_trajectkolom(shapefile):
    ahn = lees_shapefile(shapefile)
    k = koppel(ahn, kies_kolommen(ahn.velden, traject="-", profiel="-"), PROFIELEN, zoek)
    # alleen het dijkvak: 145 komt in twee trajecten voor, dus de lijn hoort bij beide profielen
    assert k.per_profiel["34-1_145.prfl"] == [0, 1, 2] and k.per_profiel["35-2_145.prfl"] == [0, 1, 2]


def test_fouten(tmp_path, shapefile):
    with pytest.raises(ValueError, match="niet gevonden"):
        kies_kolommen(lees_shapefile(shapefile).velden, dijkvak="bestaat_niet")
    with pytest.raises(ValueError, match="Geen dijkvak- of profielkolom"):
        kies_kolommen(["TRAJECT", "hoogte"])
    plat = tmp_path / "plat.shp"
    schrijf_shapefile(plat, [lijn(0, [1, 2])], ["vak_id"], soort=3)
    with pytest.raises(ValueError, match="geen hoogtes"):
        lees_shapefile(plat)


@pytest.mark.skipif(not TEST_SHAPE.exists(), reason="test_shapefiles ontbreekt")
def test_meegeleverde_shapefile():
    ahn = lees_shapefile(TEST_SHAPE)
    assert len(ahn.lijnen) == 242
    assert kies_kolommen(ahn.velden) == {"traject": "TRAJECT_ID", "dijkvak": "vak_id", "profiel": None}
    assert all(p[1] > -9990 for p in ahn.lijnen[0].profiel() if p)
    # vak_id bevat alleen het dijkvak, en alleen de vakken van de testprofielen
    vakken = {(lijn.attributen["TRAJECT_ID"], lijn.attributen["vak_id"]) for lijn in ahn.lijnen}
    assert ("34-1", "145") in vakken and len(vakken) == 11
    assert not any("_" in d for _, d in vakken)


@pytest.mark.skipif(not TEST_SHAPE.exists(), reason="test_shapefiles ontbreekt")
def test_testdata_alle_profielen_gekoppeld():
    from app import Werkruimte

    tests = Path(__file__).parent
    w = Werkruimte(prfl_map=str(tests / "test_prfl_origineel"), koppeltabel=str(tests / "test_koppeling.xlsx"),
                   ahn_shapefile=str(TEST_SHAPE))
    overzicht = w.overzicht()
    assert overzicht["ahn"]["niet_gekoppeld"] == 0
    assert all(v["ahn"] > 0 for v in overzicht["vakken"] if v["vak_id"])
