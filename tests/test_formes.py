import numpy as np
import pytest

from formes import (Assemblage, Base, Bruit, Courbure, Empilement, Fuseau, Generateur, Gigogne,
                    Ondulation, ParametresImpression, Pincement, Plis, Reseau, Torsion, generer_gcode)
from formes.bases import PROFILS
from formes.deformations import TOUTES
from formes.gcode import remplissage


def petite_base(**kw):
    return Base(**{"couches": 30, "points": 72, "hauteur": 20, "rayon": 20, **kw})


@pytest.mark.parametrize("profil", PROFILS)
def test_profils(profil):
    f = petite_base(profil=profil).construire()
    assert f.pts.shape == (31, 72, 3)
    assert np.isfinite(f.pts).all()


@pytest.mark.parametrize("cls", TOUTES)
def test_deformations_ne_touchent_pas_z(cls):
    f = petite_base().construire()
    g = cls().appliquer(f)
    assert g.pts.shape == f.pts.shape
    np.testing.assert_allclose(g.pts[:, :, 2], f.pts[:, :, 2])
    assert not np.allclose(g.pts, f.pts)


def test_module_inactif_ignore():
    gen = Generateur(petite_base(), [Torsion(angle=90, actif=False)])
    np.testing.assert_allclose(gen.forme().pts, petite_base().construire().pts)
    gen.activer("torsion")
    assert not np.allclose(gen.forme().pts, petite_base().construire().pts)


def test_gigogne_concentrique():
    a = Gigogne(nombre=3, paroi=1, jeu=1, retrait_hauteur=2).appliquer(petite_base().construire())
    assert len(a) == 3
    rayons = [np.hypot(*p.pts[0, 0, :2]) for p in a]
    np.testing.assert_allclose(rayons, [20, 18, 16], atol=1e-6)
    assert [round(p.hauteur, 6) for p in a] == [20, 18, 16]


def test_empilement_col():
    a = Empilement(nombre=2, hauteur_col=4, paroi=1, jeu=0.5, ecart_vue=0).appliquer(petite_base().construire())
    bas, haut = a.pieces
    assert bas.fond and not haut.fond
    # le col est rétréci de paroi + jeu
    assert np.hypot(*bas.pts[-1, 0, :2]) == pytest.approx(18.5)
    # chanfrein à 45° : Δz = Δr
    dz = np.diff(bas.z)
    assert (dz > 0).all()
    imp = a.pour_impression()
    assert all(p.boite()[0][2] == pytest.approx(0) for p in imp)


def test_reseau():
    a = Reseau(colonnes=2, lignes=2).appliquer(petite_base().construire())
    assert len(a) == 4


def test_remplissage_carre():
    carre = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    segs = remplissage(carre, 1.0, 0)
    assert len(segs) == 10
    assert all(abs(np.linalg.norm(s[1] - s[0]) - 10) < 1e-9 for s in segs)


@pytest.mark.parametrize("mode", ["spirale", "couches"])
def test_gcode(mode):
    gen = Generateur(petite_base(), [Fuseau(), Ondulation(), Bruit(), Plis(), Pincement(), Courbure(fleche=3)])
    texte, trajet = generer_gcode(gen.generer(), ParametresImpression(mode=mode))
    assert texte.startswith("; Généré")
    assert "M109" in texte and "M84" in texte
    assert trajet.stats["couches"] == 100
    zs = [float(l.split("Z")[1].split()[0]) for l in texte.splitlines() if l.startswith("G1 X")]
    assert min(zs) > 0
    assert max(zs) <= 20 + 1e-6
    if mode == "spirale":
        corps = zs[len(zs) // 2:]
        assert all(b >= a - 1e-9 for a, b in zip(corps, corps[1:]))  # Z ne redescend jamais


def test_gcode_plusieurs_pieces_bascule_en_couches():
    a = Gigogne().appliquer(petite_base().construire())
    _, trajet = generer_gcode(a, ParametresImpression(mode="spirale"))
    assert trajet.stats["mode"] == "couches"
    assert trajet.avertissements


def test_stl(tmp_path):
    a = Assemblage([petite_base().construire()])
    chemin = a.exporter_stl(tmp_path / "f.stl")
    n = int.from_bytes(chemin.read_bytes()[80:84], "little")
    assert chemin.stat().st_size == 84 + 50 * n
