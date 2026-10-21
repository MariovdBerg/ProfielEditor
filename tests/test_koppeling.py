import zipfile
from pathlib import Path

import pytest

from koppeling import lees_koppeltabel


def maak_xlsx(pad, rijen):
    """Minimaal .xlsx-bestand met gedeelde teksten en getallen."""
    teksten = sorted({c for rij in rijen for c in rij if isinstance(c, str)})
    def cel(ref, waarde):
        if isinstance(waarde, str):
            return f'<c r="{ref}" t="s"><v>{teksten.index(waarde)}</v></c>'
        return f'<c r="{ref}"><v>{waarde}</v></c>'
    xml_rijen = "".join(
        f'<row r="{r + 1}">' + "".join(cel(f"{chr(65 + k)}{r + 1}", w) for k, w in enumerate(rij) if w is not None)
        + "</row>" for r, rij in enumerate(rijen))
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(pad, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rns}><sheets><sheet name="Blad1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{t}</t></si>" for t in teksten) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{xml_rijen}</sheetData></worksheet>")


def test_csv_puntkomma_en_kolomherkenning(tmp_path):
    pad = tmp_path / "k.csv"
    pad.write_text("traject;vak_id;prfl_bestand;opmerking\n34-1;145;34-1_145.prfl;a\n34-1;146;34-1_146;\n",
                   encoding="utf-8-sig")
    tabel = lees_koppeltabel(pad)
    assert (tabel.kolom_dijkvak, tabel.kolom_profiel) == ("vak_id", "prfl_bestand")
    assert [(k.dijkvak, k.profiel) for k in tabel.koppelingen] == [("145", "34-1_145.prfl"), ("146", "34-1_146")]
    assert tabel.koppelingen[0].traject == "34-1"
    assert tabel.koppelingen[0].info == {"opmerking": "a"}


def test_csv_komma_cp1252_en_standaardkolommen(tmp_path):
    pad = tmp_path / "k.csv"
    pad.write_bytes("a,b\nvák 1,p1.prfl\n".encode("cp1252"))
    tabel = lees_koppeltabel(pad)
    assert tabel.koppelingen[0].dijkvak == "vák 1"
    assert tabel.koppelingen[0].profiel == "p1.prfl"


def test_opgegeven_kolommen(tmp_path):
    pad = tmp_path / "k.csv"
    pad.write_text("x;naam;bestand2\n1;A;p.prfl\n", encoding="utf-8")
    tabel = lees_koppeltabel(pad, kolom_dijkvak="naam", kolom_profiel="bestand2")
    assert (tabel.koppelingen[0].dijkvak, tabel.koppelingen[0].profiel) == ("A", "p.prfl")
    with pytest.raises(ValueError, match="niet gevonden"):
        lees_koppeltabel(pad, kolom_dijkvak="bestaat_niet")


def test_xlsx(tmp_path):
    pad = tmp_path / "k.xlsx"
    maak_xlsx(pad, [["Dijkvak", "Profiel", "km"], [145, "34-1_145.prfl", 2.5], ["DV-2", "34-1_146.prfl", None]])
    tabel = lees_koppeltabel(pad)
    assert [(k.dijkvak, k.profiel) for k in tabel.koppelingen] == [("145", "34-1_145.prfl"), ("DV-2", "34-1_146.prfl")]
    assert tabel.koppelingen[0].info == {"km": "2.5"}


def test_lege_tabel(tmp_path):
    pad = tmp_path / "k.csv"
    pad.write_text("dijkvak;profiel\n", encoding="utf-8")
    with pytest.raises(ValueError):
        lees_koppeltabel(pad)


def test_trajectkolom_en_vak_id(tmp_path):
    pad = tmp_path / "k.csv"
    pad.write_text("Traject;Dijkvak;Profiel;km\n34-1;145;34-1_145.prfl;1\n35-2;6;;2\n", encoding="utf-8")
    tabel = lees_koppeltabel(pad)
    assert (tabel.kolom_traject, tabel.kolom_dijkvak, tabel.kolom_profiel) == ("Traject", "Dijkvak", "Profiel")
    assert [(k.traject, k.dijkvak, k.vak_id, k.profiel) for k in tabel.koppelingen] == [
        ("34-1", "145", "34-1_145", "34-1_145.prfl"), ("35-2", "6", "35-2_6", "")]
    assert tabel.koppelingen[0].info == {"km": "1"}


def test_zonder_trajectkolom_en_traject_uitgeschakeld(tmp_path):
    pad = tmp_path / "k.csv"
    pad.write_text("traject;dijkvak;profiel\n34-1;145;p.prfl\n", encoding="utf-8")
    tabel = lees_koppeltabel(pad, kolom_traject="-")
    assert tabel.kolom_traject is None
    assert tabel.koppelingen[0].vak_id == "145"
    assert tabel.koppelingen[0].info == {"traject": "34-1"}


def test_alleen_traject_en_dijkvak(tmp_path):
    pad = tmp_path / "k.csv"
    pad.write_text("traject;dijkvak\n34-1;145\n", encoding="utf-8")
    tabel = lees_koppeltabel(pad)
    assert tabel.kolom_profiel is None
    assert tabel.koppelingen[0].vak_id == "34-1_145" and tabel.koppelingen[0].profiel == ""


def test_meegeleverde_test_koppeling_xlsx():
    pad = Path(__file__).parent / "test_koppeling.xlsx"
    tabel = lees_koppeltabel(pad, "dijkvak", "profiel", "traject")
    assert tabel.koppelingen[0].vak_id == "34-1_145"
    assert all(k.traject and k.dijkvak for k in tabel.koppelingen)
