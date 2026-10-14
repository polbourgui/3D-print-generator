import csv
import re

import numpy as np
import pytest

from formes.application import _lire_valeurs
from formes.plaques import (PETG_ARIANEPLAST, _e_par_mm, ParametresImpression, Plaques, ReglagePlaque, disposer,
                            exporter_fiche, exporter_plaques, exporter_stl_plaques, generer_gcode_plaques,
                            plan, serie, texte_pixels)


def machine(**kw):
    return ParametresImpression(**{**PETG_ARIANEPLAST, "vignettes": (), **kw})


def extrusions(texte):
    """(x, y, z, longueur extrudée) de chaque G1 qui extrude."""
    pos, e, res = np.zeros(3), 0.0, []
    for l in texte.splitlines():
        if not l.startswith(("G0 ", "G1 ")):
            continue
        val = dict(re.findall(r"([XYZEF])(-?[\d.]+)", l))
        nouv = pos.copy()
        for i, a in enumerate("XYZ"):
            if a in val:
                nouv[i] = float(val[a])
        if "E" in val:
            de = float(val["E"]) - e
            e = float(val["E"])
            if de > 0 and "X" in val:
                res.append((*nouv, de))
        pos = nouv
    return np.array(res)


def test_plan_combinaisons():
    cfg = plan(temp_buse=[240, 250], flux=[1.0, 1.05, 1.1])
    assert len(cfg.reglages) == 6
    assert {(r.temp_buse, r.flux) for r in cfg.reglages} == {(t, f) for t in (240, 250) for f in (1.0, 1.05, 1.1)}
    with pytest.raises(ValueError):
        plan(inconnu=[1])


def test_etiquette():
    r = ReglagePlaque(temp_buse=250, flux=1.08, vitesse=22.5, ventilateur=30, hauteur_couche=0.24)
    assert r.etiquette(4) == ["#4", "T250", "D108", "V22.5", "F30", "H24"]


def test_police_couvre_l_etiquette():
    img = texte_pixels(["#12 T245", "D105 V25"])
    assert img.shape == (12, 31) and img.any()


@pytest.mark.parametrize("face", ["dessous", "dessus"])
def test_empreinte_calee_sur_les_lignes(face):
    cfg = serie("temp_buse", [245], face=face)
    q = disposer(cfg, machine())[0][0][0]
    lw = q.reglage.largeur_ligne
    assert q.trous
    for x0, x1, y0, y1 in q.trous:
        assert 0 < x0 < x1 < q.largeur and 0 < y0 < y1 < q.longueur / 2     # dans le bas de la plaque
        for v in (x0, x1, y0, y1):                                          # bords entre deux lignes
            k = (v - q.perimetres * lw) / lw
            assert k == pytest.approx(round(k), abs=1e-6)
    assert q.grave(0) == (face == "dessous")
    assert q.grave(q.couches - 1) == (face == "dessus")


@pytest.mark.parametrize("face", ["dessous", "dessus"])
def test_maillage_ferme(face):
    q = disposer(serie("hauteur_couche", [0.2], face=face), machine())[0][0][0]
    v, f = q.maillage()
    t = v[f]
    volume = np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6
    creux = sum((x1 - x0) * (y1 - y0) for x0, x1, y0, y1 in q.trous) * q.profondeur
    assert volume == pytest.approx(q.largeur * q.longueur * q.epaisseur - creux, rel=1e-9)
    # chaque arête est parcourue autant de fois dans un sens que dans l'autre
    aretes = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    directes = {}
    for a, b in map(tuple, aretes):
        directes[(a, b)] = directes.get((a, b), 0) + 1
    assert all(directes.get((b, a), 0) == n for (a, b), n in directes.items())


def test_gcode_sequentiel_temperatures_croissantes():
    cfg = serie("temp_buse", [255, 235, 245])
    p = machine()
    lots, av = disposer(cfg, p)
    assert len(lots) == 1 and not av
    texte, trajet = generer_gcode_plaques(lots[0], cfg, p)
    assert "PRINT_START BED=75 EXTRUDER=235" in texte
    assert re.findall(r"M109 S(\d+)", texte) == ["245", "255"]
    assert texte.count("EXCLUDE_OBJECT_DEFINE") == 3
    assert [int(n) for n in re.findall(r"plaque_(\d+)_id", " ".join(trajet.stats["objets"]))] == [2, 3, 1]
    assert trajet.stats["couches"] == 3 * 10
    # chaque plaque reste dans son emprise (hors purge et amorce)
    ext = extrusions(texte)
    dans = np.zeros(len(ext), bool)
    for q in lots[0]:
        x0, y0 = q.origine
        dans |= ((ext[:, 0] >= x0 - 1e-6) & (ext[:, 0] <= x0 + q.largeur + 1e-6)
                 & (ext[:, 1] >= y0 - 1e-6) & (ext[:, 1] <= y0 + q.longueur + 1e-6))
    hors = ext[~dans]
    assert len(hors) <= 4 and (hors[:, 2] <= 0.31).all()
    assert ext[:, 2].max() == pytest.approx(2.0)


@pytest.mark.parametrize("face, gravee, pleine", [("dessous", 0.2, 2.0), ("dessus", 2.0, 0.2)])
def test_empreinte_dans_le_gcode(face, gravee, pleine):
    # lignes transversales : chaque segment reste à y constant, on peut isoler la bande du texte
    cfg = serie("temp_buse", [245], face=face, base=ReglagePlaque(motif="transversal"))
    p = machine(purge=None)
    lots, _ = disposer(cfg, p)
    texte, _ = generer_gcode_plaques(lots[0], cfg, p)
    ext = extrusions(texte)
    q = lots[0][0]
    bande = ext[:, 1] < q.origine[1] + q.longueur / 3

    def matiere(z):
        m = np.isclose(ext[:, 2], z) & bande
        return ext[m, 3].sum()

    # chaque trou coupe (hauteur / lw) lignes, sur sa largeur + lw (deux demi-cordons)
    lw = q.reglage.largeur_ligne
    retire = sum((y1 - y0) / lw * (x1 - x0 + lw) for x0, x1, y0, y1 in q.trous) * _e_par_mm(p, q.reglage)
    assert matiere(gravee) == pytest.approx(matiere(pleine) - retire, rel=0.02)


def test_debit_et_couche_par_plaque():
    cfg = plan(flux=[1.0, 1.1])
    p = machine()
    textes = [generer_gcode_plaques([q], cfg, p)[1].stats["filament_m"] for q in disposer(cfg, p)[0][0]]
    assert textes[1] / textes[0] == pytest.approx(1.1, rel=0.02)


def test_lots_et_fichiers(tmp_path):
    cfg = serie("temp_buse", [230, 235, 240, 245, 250, 255, 260])
    p = machine(plateau=(120.0, 120.0))
    res = exporter_plaques(cfg, tmp_path / "petg.gcode", p)
    assert len(res) == 7 // 2 + 1 and all(c.exists() for c, _ in res)
    assert any("lots" in a for a in res[0][1].avertissements)
    seules = exporter_plaques(cfg, tmp_path / "seule.gcode", p, par_plaque=True)
    assert [c.name for c, _ in seules][:2] == ["seule_plaque1.gcode", "seule_plaque2.gcode"]
    assert "T235" in " ".join(t for t in seules[1][0].read_text().splitlines() if t.startswith("; plaque"))
    stl = exporter_stl_plaques(cfg, tmp_path / "petg.stl", p)
    assert len(stl) == len(res) and all(s.stat().st_size > 84 for s in stl)


def test_fiche(tmp_path):
    cfg = serie("flux", [1.0, 1.05])
    chemin = exporter_fiche(cfg, tmp_path / "fiche.csv", machine())
    with open(chemin, encoding="utf-8-sig") as fh:
        lignes = list(csv.reader(fh, delimiter=";"))
    assert lignes[0][0] == "plaque" and lignes[2][6] == "1,05"


def test_lire_valeurs():
    assert _lire_valeurs("235 240;245", "temp_buse") == [235, 240, 245]
    assert _lire_valeurs("1,05 ; 1,10", "flux") == [1.05, 1.10]
    assert _lire_valeurs("1.00, 1.05", "flux") == [1.0, 1.05]
    with pytest.raises(ValueError):
        _lire_valeurs("diagonal", "motif")


def test_plaques_marlin_refroidissement():
    cfg = serie("temp_buse", [250, 240], trier_temperature=False)
    p = machine(firmware="marlin")
    texte, _ = generer_gcode_plaques(disposer(cfg, p)[0][0], cfg, p)
    assert "M109 R240" in texte


def test_reglages_dict():
    cfg = Plaques([{"temp_buse": 250}])
    assert isinstance(cfg.reglages[0], ReglagePlaque) and cfg.reglages[0].temp_buse == 250
