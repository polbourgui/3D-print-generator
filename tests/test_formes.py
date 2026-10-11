import numpy as np
import pytest

from formes import (Assemblage, Base, Dentelle, Luminaire, Bec, Bruit, Couvercle, Courbure, Ecailles, Empilement, Facettes,
                    Fuseau, Generateur, Gigogne, Losanges, Nervures, Ondulation, ParametresImpression,
                    Pincement, Plis, Reseau, Torsion, generer_gcode)
from formes.gcode import _porte_a_faux
from formes.geometrie import aire_signee
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


def test_classes_sans_parentheses():
    gen = Generateur(petite_base(), [Torsion], Couvercle)
    assert isinstance(gen.emboitement, Couvercle) and isinstance(gen.deformations[0], Torsion)
    assert len(gen.generer()) == 2


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


@pytest.mark.parametrize("cls", [Nervures, Losanges, Ecailles, Facettes])
def test_motifs_sans_couture(cls):
    # le motif doit se refermer : pas de saut entre le dernier et le premier point
    f = cls().appliquer(petite_base(points=360).construire())
    pas = np.linalg.norm(np.diff(f.pts[:, :, :2], axis=1, append=f.pts[:, :1, :2]), axis=-1)
    assert pas[:, -1].max() < 3 * np.median(pas)


def test_facettes_polygone():
    f = Facettes(nombre=5, vrille=0, melange=1).appliquer(petite_base(points=360).construire())
    c = f.pts[0, :, :2]
    # 5 sommets sur le cercle d'origine, les autres points sur les cordes
    r = np.hypot(*c.T)
    assert np.isclose(r, 20).sum() == 5
    assert aire_signee(c) == pytest.approx(0.5 * 5 * 20 ** 2 * np.sin(2 * np.pi / 5))


def test_bec_seulement_en_haut_et_dans_sa_direction():
    f0 = petite_base().construire()
    f = Bec(longueur=5, direction=90, largeur=60, debut=0.5).appliquer(f0)
    d = np.linalg.norm(f.pts - f0.pts, axis=-1)
    assert d[: len(d) // 2].max() == pytest.approx(0)
    i = np.argmax(d[-1])
    assert np.degrees(np.arctan2(f.pts[-1, i, 1], f.pts[-1, i, 0])) == pytest.approx(90, abs=2)
    assert d[-1].max() == pytest.approx(5, abs=0.1)


def test_ecailles_sans_surplomb():
    f = Ecailles(epaisseur=1, rangs=4).appliquer(petite_base(couches=120).construire())
    assert _porte_a_faux(f) < 45


def test_retourner():
    f = petite_base().construire()
    f.ferme_haut, f.fond = True, False
    r = f.retourner()
    assert r.retournee and r.fond and not r.ferme_haut
    assert (np.diff(r.z) > 0).all()
    assert aire_signee(r.pts[0, :, :2]) > 0                 # toujours CCW
    np.testing.assert_allclose(r.retourner().pts, f.pts, atol=1e-9)


def test_couvercle():
    vase = Fuseau(echelle_haut=0.6).appliquer(petite_base().construire())
    a = Couvercle(epaisseur=0.8, debord=1, hauteur_col=4, paroi=0.8, jeu=0.2, ecart_vue=0).appliquer(vase)
    assert len(a) == 2
    _, couv = a.pieces
    r_haut = np.hypot(*vase.pts[-1, :, :2].T).mean()
    # vue : col dans l'ouverture (rétréci de paroi + jeu), plateau au-dessus du bord
    assert np.hypot(*couv.pts[0, :, :2].T).mean() == pytest.approx(r_haut - 1, abs=0.05)
    assert np.hypot(*couv.pts[-1, :, :2].T).mean() == pytest.approx(r_haut + 1, abs=0.05)
    assert couv.boite()[0][2] == pytest.approx(vase.z[-1] - 4)
    # impression : couvercle retourné, posé à côté, plateau en bas, sans surplomb
    imp = a.pour_impression()
    c = imp.pieces[1]
    assert c.fond and not c.ferme_haut and c.boite()[0][2] == pytest.approx(0)
    assert np.hypot(*(c.pts[0, :, :2] - c.centres()[0]).T).mean() == pytest.approx(r_haut + 1, abs=0.05)
    assert _porte_a_faux(c) == pytest.approx(0)
    assert imp.pieces[0].boite()[1][0] < c.boite()[0][0]   # pas de chevauchement
    texte, trajet = generer_gcode(a, ParametresImpression(vignettes=()))
    assert trajet.stats["mode"] == "couches"
    assert texte.count("EXCLUDE_OBJECT_DEFINE") == 2


def test_remplissage_carre():
    carre = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    segs = remplissage(carre, 1.0, 0)
    assert len(segs) == 10
    assert all(abs(np.linalg.norm(s[1] - s[0]) - 10) < 1e-9 for s in segs)


@pytest.mark.parametrize("mode", ["spirale", "couches"])
def test_gcode(mode):
    gen = Generateur(petite_base(), [Fuseau(), Ondulation(), Bruit(), Plis(), Pincement(), Courbure(fleche=3),
                                     Nervures(), Losanges(), Ecailles(), Facettes(), Bec()])
    texte, trajet = generer_gcode(gen.generer(), ParametresImpression(mode=mode, firmware="marlin",
                                                                      vignettes=()))
    assert texte.startswith("; generated by generateur-formes")
    assert "M109" in texte and "M84" in texte
    assert "EXCLUDE_OBJECT" not in texte
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


def gcode_klipper(assemblage, **kw):
    kw.setdefault("vignettes", ())
    return generer_gcode(assemblage, ParametresImpression(firmware="klipper", **kw))


def test_klipper_exclude_object_et_kamp():
    a = Gigogne(nombre=3, retrait_hauteur=4).appliquer(petite_base().construire())
    texte, trajet = gcode_klipper(a, maillage_adaptatif=True, purge="LINE_PURGE")
    lignes = texte.splitlines()
    defs = [l for l in lignes if l.startswith("EXCLUDE_OBJECT_DEFINE")]
    assert len(defs) == 3
    # KAMP : les objets doivent être définis avant la macro de démarrage et le maillage
    i_def = lignes.index(defs[-1])
    i_start = next(i for i, l in enumerate(lignes) if l.startswith("PRINT_START"))
    i_mesh = lignes.index("BED_MESH_CALIBRATE ADAPTIVE=1")
    i_purge = lignes.index("LINE_PURGE")
    assert i_def < i_start < i_mesh < i_purge
    assert "M109" not in texte and "G28" not in texte     # gérés par PRINT_START
    assert lignes[-1] != "M84" and "PRINT_END" in lignes
    # le polygone est du JSON valide (Klipper le lit avec json.loads)
    import json
    poly = json.loads(defs[0].split("POLYGON=")[1])
    assert len(poly) >= 3 and all(len(p) == 2 for p in poly)
    # START / END équilibrés, jamais imbriqués, et chaque objet se termine rétracté
    ouvert = None
    for i, l in enumerate(lignes):
        if l.startswith("EXCLUDE_OBJECT_START"):
            assert ouvert is None
            ouvert = l.split("NAME=")[1]
        elif l.startswith("EXCLUDE_OBJECT_END"):
            assert ouvert == l.split("NAME=")[1]
            assert lignes[i - 1].startswith("G1 E")       # rétraction
            ouvert = None
        elif l.startswith("G1 X") and " E" in l:
            assert ouvert is not None                      # toute extrusion appartient à un objet
    assert ouvert is None
    assert f"SET_PRINT_STATS_INFO TOTAL_LAYER={trajet.stats['couches']}" in lignes
    assert "SET_PRINT_STATS_INFO CURRENT_LAYER=1" in lignes


def test_klipper_sans_macro_et_retraction_firmware():
    texte, _ = gcode_klipper(petite_base().construire(), macro_debut=None, macro_fin=None,
                             retraction_firmware=True, mode="couches")
    assert "M109 S210" in texte and "G28" in texte and "M84" in texte
    assert "G10" in texte and "G11" in texte
    assert texte.isascii()


def test_metadonnees_moonraker():
    import re
    texte, trajet = gcode_klipper(petite_base().construire())
    assert re.search(r"; generated by (.+?) on \d{4}-\d{2}-\d{2} at \d{2}:\d{2}:\d{2}", texte)
    pied = texte[-3000:]
    for cle in ["; filament used [mm] = ", "; total filament used [g] = ", "; total layers count = 100",
                "; estimated printing time (normal mode) = ", "; layer_height = 0.2",
                "; first_layer_temperature = 210", "; first_layer_bed_temperature = 60",
                "; nozzle_diameter = 0.4", "; filament_type = PLA"]:
        assert cle in pied, cle
    assert re.findall(r";BEFORE_LAYER_CHANGE\n;(\d+\.?\d*)", texte)[-1] == "20.000"


def test_vignettes():
    pytest.importorskip("matplotlib")
    import base64
    import re
    texte, _ = gcode_klipper(petite_base().construire(), vignettes=((32, 32), (300, 300)))
    blocs = re.findall(r"; thumbnail begin (\d+)x(\d+) (\d+)\n((?:; .*\n)+?); thumbnail end", texte)
    assert [(b[0], b[1]) for b in blocs] == [("32", "32"), ("300", "300")]
    for l, h, n, corps in blocs:
        data = "".join(x[2:] for x in corps.splitlines())
        assert len(data) == int(n)
        assert all(len(x) <= 80 for x in corps.splitlines())
        png = base64.b64decode(data)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert int.from_bytes(png[16:20], "big") == int(l)
        assert int.from_bytes(png[20:24], "big") == int(h)


def test_application(tmp_path):
    pytest.importorskip("ipywidgets")
    from formes.application import Application

    app = Application(tmp_path)
    w = app.widgets
    w[("Nervures", "actif")].value = True
    w[("Nervures", "nombre")].value = 20
    w[("Emboitement", "choix")].value = "Couvercle"
    w[("Impression", "filament")].value = "PETG"
    w[("Impression", "imprimante")].value = "Voron 2.4 – 350"
    assert app.impression.temp_buse == 235 and app.impression.plateau == (350.0, 350.0)
    app._deplacer(app.deformations[-1], -1)
    assert "2 pièces" in app.infos.value
    w[("Emboitement", "choix")].value = "Luminaire"
    w[("Luminaire", "culot")].value = "E14"
    w[("Luminaire", "montage")].value = "a poser"
    assert "douille E14" in app.infos.value
    w[("Emboitement", "choix")].value = "Aucun"
    w[("Dentelle", "actif")].value = True
    assert "dentelle" in app.infos.value
    app.calibration_dentelle()
    assert app.base.rayon == 20 and app.dentelle.maille_haut == 8
    w[("Emboitement", "choix")].value = "Couvercle"
    app.exporter_tout()
    assert len(list(tmp_path.glob(f"{app.nom.value}.*"))) == 3
    app.sauvegarder()
    autre = Application(tmp_path)
    autre.charger(app.nom.value)
    assert autre.reglages() == app.reglages()


def test_remplissage_avec_trou():
    carre = np.array([[0, 0], [20, 0], [20, 20], [0, 20]], float)
    a = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    trou = 10 + 5 * np.column_stack([np.cos(a), np.sin(a)])
    for s in remplissage([carre, trou], 0.5, 0):
        milieu = s.mean(0)
        assert np.linalg.norm(milieu - 10) > 5 - 1e-6     # aucun segment ne traverse le trou


def lampe(**kw):
    base = Base(rayon=50, hauteur=40, couches=40, points=180)
    return Generateur(base, [Fuseau(echelle_haut=0.7, ventre=0)], Luminaire(**kw))


@pytest.mark.parametrize("culot, d", [("E27", 40), ("E14", 28), ("GU10", 50)])
def test_luminaire_suspension(culot, d):
    a = lampe(culot=culot, jeu=0.5).generer()
    f = a.pieces[0]
    assert f.douille_haut == (d + 0.5, 0.0) and not f.fond and f.ferme_haut and f.retournee
    imp = a.pour_impression().pieces[0]
    assert imp.fond and imp.douille_bas == (d + 0.5, 0.0) and imp.douille_haut is None
    texte, trajet = generer_gcode(a, ParametresImpression(vignettes=(), couches_fond=5))
    assert trajet.stats["mode"] == "spirale" and not trajet.avertissements
    # 1re couche : un périmètre autour du perçage, bord intérieur au bon diamètre
    centre = np.array([110.0, 110.0])
    for typ, pts in trajet.segments:
        if typ == "remplissage" and pts[:, 2].max() < 0.25:
            assert np.linalg.norm(pts[:, :2] - centre, axis=1).min() > (d + 0.5) / 2
    rayons = [np.linalg.norm(pts[:, :2] - centre, axis=1).mean() for typ, pts in trajet.segments
              if typ == "perimetre" and pts[:, 2].max() < 0.25]
    assert min(rayons) == pytest.approx((d + 0.5) / 2 + 0.45 / 2, abs=0.1)


def test_luminaire_a_poser_avec_manchon():
    a = lampe(culot="perso", diametre_perso=30, jeu=0, montage="a poser", manchon=6).generer()
    f = a.pieces[0]
    assert f.fond and f.douille_bas == (30, 6) and not f.retournee
    v, t = f.maillage()
    assert np.isfinite(v).all() and t.max() < len(v)
    texte, trajet = generer_gcode(a, ParametresImpression(vignettes=()))
    assert trajet.stats["mode"] == "couches"
    centre = np.array([110.0, 110.0])
    manchon = [pts for typ, pts in trajet.segments if typ == "perimetre"
               and abs(np.linalg.norm(pts[:, :2] - centre, axis=1).mean() - 15.225) < 0.1]
    assert max(pts[:, 2].max() for pts in manchon) == pytest.approx(6.0)


def test_luminaire_trop_etroit():
    with pytest.raises(ValueError, match="trop étroit"):
        Generateur(Base(rayon=20), [], Luminaire(culot="E27")).generer()


def _cylindre_fuseau():
    return Fuseau(echelle_haut=0.7, ventre=0.2).appliquer(
        Base(rayon=30, hauteur=60, couches=60, points=240).construire())


def _sur_segment(p, a, b, tol=1e-6):
    t = np.clip(np.dot(p - a, b - a) / max(np.dot(b - a, b - a), 1e-12), 0, 1)
    return np.linalg.norm(a + t * (b - a) - p) < tol


@pytest.mark.parametrize("motif_", ["losanges", "triangles"])
@pytest.mark.parametrize("kw", [{}, {"hauteur_maille": 3, "maille_haut": 8, "cellules": 9}])
def test_dentelle_treillis(motif_, kw):
    f = _cylindre_fuseau()
    d = Dentelle(motif=motif_, **kw)
    etages = d.trajet(f, 0.2, 0.8, largeur_ligne=0.45)
    mvts = [m for e in etages for m in e]
    # trajet continu : chaque mouvement part de la fin du précédent
    for (_, a, _), (_, b, _) in zip(mvts, mvts[1:]):
        np.testing.assert_allclose(a[-1], b[0], atol=1e-9)
    z = d.points(etages)[:, 2]
    assert z.min() == pytest.approx(0.8) and z.max() == pytest.approx(60)
    treillis = [e for e in etages if any(t == "montee" for t, _, _ in e)]
    assert len(treillis) >= 5
    anneau_prec = None
    for e in treillis:
        z_bas = e[0][1][0, 2]
        anneau = np.vstack([p for t, p, _ in e if t == "anneau"])
        z_nominal = anneau[-1, 2] + d.pression
        for t, pts, pause in e:
            assert len(pts) == 2                                  # uniquement des segments droits
            assert pts[:, 2].min() >= z_bas - 1e-9                # jamais sous l'anneau d'appui
            if t == "montee":
                assert pts[1, 2] == pytest.approx(z_nominal + d.affaissement) and pause == d.pause
            if t in ("anneau", "descente"):
                assert pause == d.pause_noeud                     # soudures
            if t == "descente" and anneau_prec is not None:
                # chaque descente se pose sur l'anneau du dessous
                fin = pts[-1]
                assert fin[2] == pytest.approx(z_bas)
                assert any(_sur_segment(fin[:2], a[:2], b[:2], 1e-6)
                           for a, b in zip(anneau_prec, anneau_prec[1:]))
        # l'anneau passe par tous les sommets des montées, enfoncé de « pression »
        sommets = [p[1] - [0, 0, d.affaissement + d.pression] for t, p, _ in e if t == "montee"]
        for s_ in sommets:
            assert np.min(np.linalg.norm(anneau - s_, axis=1)) < 1e-6
        # aucune descente plus raide que le flanc de la buse (le brin frotterait dessus)
        for t, pts, _ in e:
            if t == "descente":
                dz = pts[0, 2] - pts[1, 2]
                assert np.degrees(np.arctan2(dz, np.linalg.norm(pts[0, :2] - pts[1, :2]))) <= d.angle_buse + 1e-6
        # la montée de raccord ne repasse pas sur un brin existant
        montees = [p for t, p, _ in e if t == "montee_lente"]
        assert np.linalg.norm(montees[-1][0, :2] - montees[0][0, :2]) > 0.8
        anneau_prec = anneau


def test_dentelle_angle_buse_trop_haut():
    # étages très hauts pour des mailles étroites : impossible de rester sous 40°, on le signale
    f = Base(rayon=20, hauteur=40, couches=40, points=180).construire()
    d = Dentelle(cellules=40, hauteur_maille=10)
    r = d.resume(f, 0.2)
    assert not r["buse_ok"] and r["descente_max"] > d.angle_buse
    g = Generateur(Base(rayon=20, hauteur=40, couches=40, points=180), [], dentelle=d)
    _, trajet = generer_gcode(g.generer(), ParametresImpression(vignettes=()))
    assert any("touchera la buse" in a for a in trajet.avertissements)


def test_dentelle_debit_fil():
    d = Dentelle(debit_fil=0.8)
    assert d.debit("montee") == d.debit("anneau") == 0.8 and d.debit("bord") == 1.0
    assert d.vitesse("montee_lente") == d.vitesse_montee / 2


def test_dentelle_anciens_reglages():
    assert Dentelle(motif="zigzag").motif == "losanges"


def test_dentelle_gcode_vitesse_z():
    import re
    g = Generateur(Base(rayon=25, hauteur=30, couches=40, points=180), [], dentelle=Dentelle())
    texte, trajet = generer_gcode(g.generer(), ParametresImpression(vignettes=(), vitesse_z_max=6))
    assert trajet.stats["mode"] == "dentelle"
    assert "M106 S255" in texte and "G4 P500" in texte and "G4 P200" in texte
    assert re.search(r"; max_z_height = 30\.000", texte)
    pos, F, vz = None, None, 0.0
    for l in texte.splitlines():
        if l.startswith(("G1 X", "G0 X")):
            v = {k: float(x) for k, x in re.findall(r"([XYZF])(-?[\d.]+)", l)}
            p = np.array([v["X"], v["Y"], v["Z"]])
            if l.startswith("G1"):
                F = v.get("F", F)
                d = np.linalg.norm(p - pos)
                if d > 0:
                    vz = max(vz, F / 60 * abs(p[2] - pos[2]) / d)
            pos = p
    assert vz <= 6 * 1.01        # coordonnées arrondies au µm dans le G-code


def test_dentelle_plusieurs_pieces_ignoree():
    g = Generateur(petite_base(), [], Gigogne(nombre=2), Dentelle())
    _, trajet = generer_gcode(g.generer(), ParametresImpression(vignettes=()))
    assert trajet.stats["mode"] == "couches"
    assert any("dentelle ignorée" in a for a in trajet.avertissements)


def test_dentelle_abat_jour():
    g = Generateur(Base(rayon=45, hauteur=50, couches=50, points=180), [Fuseau(echelle_haut=0.6, ventre=0)],
                   Luminaire(culot="E14"), Dentelle(cellules=28))
    a = g.generer()
    from formes.visualisation import trajet_apercu
    brins = trajet_apercu(a.pieces[0])
    assert brins[:, 2].min() >= -1e-6 and brins[:, 2].max() <= 50 + 1e-6
    texte, trajet = generer_gcode(a, ParametresImpression(vignettes=(), couches_fond=6))
    assert trajet.stats["mode"] == "dentelle" and not trajet.avertissements
