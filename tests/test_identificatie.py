from identificatie import identificeer, koppel_versies, ontleed_bestandsnaam


def test_ontleed_bestandsnaam():
    assert ontleed_bestandsnaam("34-1_145.prfl") == ("34-1", "145")
    assert ontleed_bestandsnaam("34a-1_50_aangepast.prfl") == ("34a-1", "50")
    assert ontleed_bestandsnaam("35-2_6_damwand.prfl") == ("35-2", "6")
    assert ontleed_bestandsnaam("dijk_noord.prfl") == (None, None)   # 'dijk' lijkt niet op een traject
    assert ontleed_bestandsnaam("34-1.prfl") == (None, None)


def test_identificeer_koppeltabel_gaat_voor():
    # traject uit de koppeltabel wint, ook als de bestandsnaam iets anders zegt
    assert identificeer("34-1", "", "35-2_6.prfl") == {
        "traject": "34-1", "dijkvak": "6", "vak_id": "34-1_6",
        "bron": {"traject": "koppeltabel", "dijkvak": "bestandsnaam"}}
    assert identificeer("", "", None)["bron"] == {"traject": None, "dijkvak": None}


def namen(versies):
    return {o: [v.naam for v in vs] for o, vs in versies.items()}


def test_achtervoegsel_eerst():
    versies = koppel_versies(["a.prfl"], {"a_aangepast.prfl": 1, "a_v2.prfl": 2}, "_aangepast")
    # stap 1 vindt een versie, dus a_v2 wordt niet meer gezocht
    assert namen(versies) == {"a.prfl": ["a_aangepast.prfl"]}


def test_langste_origineel_wint_en_scheidingsteken_verplicht():
    versies = koppel_versies(["34-1_14.prfl", "34-1_145.prfl"],
                             {"34-1_145_x.prfl": 1, "34-1_14-y.prfl": 1, "34-1_1450.prfl": 1}, "_aangepast")
    assert namen(versies) == {"34-1_14.prfl": ["34-1_14-y.prfl"], "34-1_145.prfl": ["34-1_145_x.prfl"]}
    assert versies["34-1_14.prfl"][0].achtervoegsel == "-y"


def test_dubbele_naam_en_volgorde():
    versies = koppel_versies(["b.prfl"], {"B.prfl": 5, "b_oud.prfl": 1, "b nieuw.prfl": 9}, "_aangepast")
    assert namen(versies) == {"b.prfl": ["b nieuw.prfl", "B.prfl", "b_oud.prfl"]}   # nieuwste eerst
    assert [v.dubbel for v in versies["b.prfl"]] == [False, True, False]


def test_eigen_naam_overslaan():
    versies = koppel_versies(["b.prfl"], {"b.prfl": 1, "b_x.prfl": 1}, "_aangepast", eigen_naam_overslaan=True)
    assert namen(versies) == {"b.prfl": ["b_x.prfl"]}
