"""Génération de G-code pour imprimante FDM (Klipper ou Marlin, extrusion absolue).

Klipper (par défaut) :
- vignettes PNG intégrées (aperçu Mainsail / Fluidd / KlipperScreen) ;
- métadonnées lues par Moonraker (durée, filament, couches, températures…) ;
- ``EXCLUDE_OBJECT_DEFINE / START / END`` pour annuler une pièce en cours
  d'impression, déclarés *avant* la macro de démarrage : c'est ce dont KAMP
  (et ``BED_MESH_CALIBRATE ADAPTIVE=1``) a besoin pour le maillage et la purge
  adaptatifs ;
- ``SET_PRINT_STATS_INFO`` pour l'affichage « couche x / n ».

Deux modes :
- ``spirale`` : mode vase — une seule paroi, Z monte en continu, aucune couture.
                Réservé à une pièce unique.
- ``couches`` : couche par couche, une paroi par pièce, avec rétractions entre
                pièces. Permet d'imprimer plusieurs pièces (gigognes en place,
                modules d'empilement posés côte à côte...).

Dans les deux cas, les pièces avec ``fond=True`` reçoivent un fond plein
(périmètre + remplissage rectiligne croisé) sur ``couches_fond`` couches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from .geometrie import Assemblage, Forme, decaler_contour, enveloppe_convexe, normales_2d

VERSION = "0.2.0"


@dataclass
class ParametresImpression:
    firmware: str = "klipper"          # "klipper" | "marlin"
    mode: str = "spirale"              # "spirale" | "couches"
    hauteur_couche: float = 0.2
    largeur_ligne: float = 0.45        # ≈ diamètre de buse + 10 %
    diametre_filament: float = 1.75
    flux: float = 1.0
    couches_fond: int = 4
    temp_buse: int = 210
    temp_plateau: int = 60
    vitesse: float = 25.0              # mm/s, parois
    vitesse_premiere_couche: float = 15.0
    vitesse_remplissage: float = 35.0
    vitesse_deplacement: float = 120.0
    retraction: float = 1.0            # mm (0 pour désactiver)
    vitesse_retraction: float = 35.0
    ventilateur: int = 255             # 0..255, activé à partir de la 2e couche
    plateau: tuple = (220.0, 220.0)    # dimensions X, Y (mm)
    hauteur_max: float = 250.0
    centre: tuple | None = None        # centre de la pièce ; None = centre du plateau
    densite_g_cm3: float = 1.24        # PLA
    angle_max_porte_a_faux: float = 50.0

    # -- Klipper ---------------------------------------------------------------
    # Macro de démarrage ({temp_plateau}, {temp_buse}, {...} sont remplacés).
    # None : démarrage standard (M190/M109/G28) sans macro.
    macro_debut: str | None = "PRINT_START BED={temp_plateau} EXTRUDER={temp_buse}"
    macro_fin: str | None = "PRINT_END"
    # Maillage adaptatif après la macro de démarrage (Klipper ≥ 0.12 ou KAMP).
    # À laisser à False si votre PRINT_START appelle déjà BED_MESH_CALIBRATE.
    maillage_adaptatif: bool = False
    # Purge : "interne" (ligne au bord de la pièce), nom d'une macro
    # ("LINE_PURGE", "VORON_PURGE" pour KAMP) ou None si PRINT_START purge déjà.
    purge: str | None = "interne"
    exclude_object: bool = True
    retraction_firmware: bool = False  # G10/G11 ([firmware_retraction])

    # -- métadonnées (Moonraker / Mainsail) -------------------------------------
    diametre_buse: float = 0.4
    filament_type: str = "PLA"
    filament_nom: str = "PLA"
    filament_couleur: str = "#E8B04A"
    vignettes: tuple = ((32, 32), (300, 300))   # () pour désactiver


@dataclass
class Trajet:
    """Trajet d'outil, pour la visualisation : liste de (type, points (M,3))."""

    segments: list = field(default_factory=list)
    avertissements: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Remplissage rectiligne d'un contour
# ---------------------------------------------------------------------------

def remplissage(contour: np.ndarray, espacement: float, angle_deg: float) -> list[np.ndarray]:
    """Segments de remplissage (liste de (2,2)) d'un polygone, en zigzag."""
    a = np.radians(angle_deg)
    rot = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])  # monde → local
    p = contour @ rot.T
    q = np.roll(p, -1, axis=0)
    ymin, ymax = p[:, 1].min(), p[:, 1].max()
    segs = []
    for i, y in enumerate(np.arange(ymin + espacement / 2, ymax, espacement)):
        traverse = (p[:, 1] <= y) != (q[:, 1] <= y)
        if not traverse.any():
            continue
        p1, p2 = p[traverse], q[traverse]
        xs = np.sort(p1[:, 0] + (y - p1[:, 1]) * (p2[:, 0] - p1[:, 0]) / (p2[:, 1] - p1[:, 1]))
        paires = [(xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)]
        if i % 2:
            paires = [(b, c) for c, b in reversed(paires)]
        for x0, x1 in paires:
            if abs(x1 - x0) > espacement * 0.3:
                segs.append(np.array([[x0, y], [x1, y]]) @ rot)  # local → monde
    return segs


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

class _Ecrivain:
    def __init__(self, p: ParametresImpression):
        self.p = p
        self.lignes: list[str] = []
        self.e = 0.0
        self.pos = np.zeros(3)
        self.retracte = False
        self.filament = 0.0
        self.temps = 0.0
        self.trajet = Trajet()
        section = np.pi * (p.diametre_filament / 2) ** 2
        self.e_par_mm = p.largeur_ligne * p.hauteur_couche * p.flux / section

    def __call__(self, ligne: str):
        self.lignes.append(ligne)

    def _retracter(self):
        if self.retracte:
            return
        if self.p.retraction_firmware:
            self("G10")
        elif self.p.retraction > 0:
            self.e -= self.p.retraction
            self(f"G1 E{self.e:.5f} F{self.p.vitesse_retraction * 60:.0f}")
        else:
            return
        self.retracte = True

    def _reamorcer(self):
        if not self.retracte:
            return
        if self.p.retraction_firmware:
            self("G11")
        else:
            self.e += self.p.retraction
            self(f"G1 E{self.e:.5f} F{self.p.vitesse_retraction * 60:.0f}")
        self.retracte = False

    def deplacer(self, pt):
        pt = np.asarray(pt, float)
        d = np.linalg.norm(pt[:2] - self.pos[:2])
        if d < 1e-6 and abs(pt[2] - self.pos[2]) < 1e-6:
            return
        if d > 2.0 and self.filament > 0:
            self._retracter()
        self(f"G0 X{pt[0]:.3f} Y{pt[1]:.3f} Z{pt[2]:.3f} F{self.p.vitesse_deplacement * 60:.0f}")
        self.trajet.segments.append(("deplacement", np.array([self.pos, pt])))
        self.temps += d / self.p.vitesse_deplacement
        self.pos = pt

    def extruder(self, pts: np.ndarray, vitesse: float, type_: str, deplacer=True):
        pts = np.asarray(pts, float)
        if deplacer:
            self.deplacer(pts[0])
            pts = pts[1:]
        self._reamorcer()
        f = f" F{vitesse * 60:.0f}"
        prec = self.pos
        for pt in pts:
            d = np.linalg.norm(pt - prec)
            if d < 1e-4:
                continue
            self.e += d * self.e_par_mm
            self.filament += d * self.e_par_mm
            self.temps += d / vitesse
            self(f"G1 X{pt[0]:.3f} Y{pt[1]:.3f} Z{pt[2]:.3f} E{self.e:.5f}{f}")
            f = ""
            prec = pt
        self.trajet.segments.append((type_, np.vstack([self.pos[None], pts])))
        self.pos = prec


def _ferme(c: np.ndarray, z: float) -> np.ndarray:
    """Contour 2D → boucle 3D fermée."""
    boucle = np.vstack([c, c[:1]])
    return np.column_stack([boucle, np.full(len(boucle), z)])


def _fond(w: _Ecrivain, contour: np.ndarray, z: float, k: int, vitesse: float):
    p = w.p
    w.extruder(_ferme(contour, z), vitesse, "perimetre")
    interieur = decaler_contour(contour, -0.85 * p.largeur_ligne)
    v_remp = p.vitesse_remplissage if k else vitesse
    for s in remplissage(interieur, p.largeur_ligne, 45 + 90 * (k % 2)):
        seg = np.column_stack([s, [z, z]])
        # segment voisin : on enchaîne sans déplacement (zigzag continu)
        proche = np.linalg.norm(seg[0, :2] - w.pos[:2]) < 2 * p.largeur_ligne
        w.extruder(seg, v_remp, "remplissage", deplacer=not proche)


def _porte_a_faux(f: Forme) -> float:
    """Angle maximal de surplomb (degrés) entre deux couches de calcul."""
    dz = np.diff(f.z)
    pire = 0.0
    for i in range(len(dz)):
        if dz[i] <= 1e-9:
            continue
        n = normales_2d(f.pts[i, :, :2])
        sortie = np.einsum("ij,ij->i", f.pts[i + 1, :, :2] - f.pts[i, :, :2], n).max()
        pire = max(pire, np.degrees(np.arctan2(max(sortie, 0), dz[i])))
    return pire


def _nom_objet(nom: str, i: int) -> str:
    """Nom compatible EXCLUDE_OBJECT (pas d'espace ni de caractère spécial)."""
    propre = re.sub(r"[^A-Za-z0-9_-]+", "_", nom).strip("_") or "piece"
    return f"{propre}_id_{i}"


def _polygone_objet(q: Forme, marge: float = 1.0, max_points: int = 32) -> np.ndarray:
    """Empreinte convexe de la pièce, élargie de ``marge`` et simplifiée."""
    env = enveloppe_convexe(q.pts.reshape(-1, 3))
    if len(env) >= 3:
        env = decaler_contour(env, marge)
        if len(env) > max_points:
            env = env[np.linspace(0, len(env), max_points, endpoint=False).astype(int)]
    return env


def _duree_texte(secondes: float) -> str:
    s = int(round(secondes))
    j, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    morceaux = [f"{j}d"] * bool(j) + [f"{h}h"] * bool(j or h) + [f"{m}m"] * bool(j or h or m)
    return " ".join(morceaux + [f"{s}s"])


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def generer_gcode(assemblage: Assemblage | Forme, p: ParametresImpression | None = None,
                  nom: str = "forme"):
    """Renvoie (texte G-code, Trajet)."""
    p = p or ParametresImpression()
    if p.firmware not in ("klipper", "marlin"):
        raise ValueError(f"firmware inconnu : {p.firmware!r} (klipper | marlin)")
    klipper = p.firmware == "klipper"
    if isinstance(assemblage, Forme):
        assemblage = Assemblage([assemblage])
    pieces = assemblage.pour_impression().pieces
    w = _Ecrivain(p)
    av = w.trajet.avertissements

    # centrage sur le plateau
    mn, mx = Assemblage(pieces).boite()
    centre = np.array(p.centre if p.centre is not None else (p.plateau[0] / 2, p.plateau[1] / 2))
    decal = centre - (mn[:2] + mx[:2]) / 2
    pieces = [q.translater(*decal, dz=-q.boite()[0][2]) for q in pieces]
    mn, mx = Assemblage(pieces).boite()
    if mn[0] < 0 or mn[1] < 0 or mx[0] > p.plateau[0] or mx[1] > p.plateau[1]:
        av.append(f"la pièce dépasse du plateau ({mx[0] - mn[0]:.0f} × {mx[1] - mn[1]:.0f} mm)")
    if mx[2] > p.hauteur_max:
        av.append(f"hauteur {mx[2]:.0f} mm > hauteur max {p.hauteur_max:.0f} mm")
    for q in pieces:
        a = _porte_a_faux(q)
        if a > p.angle_max_porte_a_faux:
            av.append(f"{q.nom} : surplomb de {a:.0f}° (> {p.angle_max_porte_a_faux:.0f}°)")

    mode = p.mode
    if mode == "spirale" and len(pieces) > 1:
        av.append(f"{len(pieces)} pièces : le mode spirale est remplacé par le mode couches")
        mode = "couches"

    h = p.hauteur_couche
    hauts = [q.z[-1] for q in pieces]
    nb_couches = int(np.floor(max(hauts) / h + 1e-6))
    objets = klipper and p.exclude_object
    noms = [_nom_objet(q.nom, i) for i, q in enumerate(pieces)]

    # -- en-tête : identification, vignettes, objets ------------------------------
    # Moonraker reconnaît « ; generated by <nom> <version> on <date> at <heure> »
    # et lit alors les métadonnées au format PrusaSlicer (bloc de fin de fichier).
    w(f"; generated by generateur-formes {VERSION} on {datetime.now():%Y-%m-%d at %H:%M:%S}")
    w(";")
    if p.vignettes:
        try:
            from .vignettes import vignettes_gcode
            for ligne in vignettes_gcode(pieces, p.vignettes):
                w(ligne)
            w(";")
        except ImportError:
            av.append("matplotlib absent : G-code généré sans vignette d'aperçu")
    w(f"; {nom} - mode {mode}, firmware {p.firmware}")
    w(f"; {len(pieces)} piece(s), {nb_couches} couches de {h} mm, ligne {p.largeur_ligne} mm")
    w(";")
    if objets:
        for n, q in zip(noms, pieces):
            poly = _polygone_objet(q)
            c = q.centres().mean(axis=0)
            pts = ",".join(f"[{x:.3f},{y:.3f}]" for x, y in poly)
            w(f"EXCLUDE_OBJECT_DEFINE NAME={n} CENTER={c[0]:.3f},{c[1]:.3f} POLYGON=[{pts}]")
    if klipper:
        w(f"SET_PRINT_STATS_INFO TOTAL_LAYER={nb_couches}")

    # -- démarrage ---------------------------------------------------------------
    w("M107")
    if klipper and p.macro_debut:
        w(p.macro_debut.format(**vars(p)))
    else:
        w(f"M140 S{p.temp_plateau}")
        w(f"M104 S{p.temp_buse}")
        w(f"M190 S{p.temp_plateau}")
        w(f"M109 S{p.temp_buse}")
        w("G28")
    if klipper and p.maillage_adaptatif:
        w("BED_MESH_CALIBRATE ADAPTIVE=1")
    w("G21 ; millimetres")
    w("G90 ; coordonnees absolues")
    w("M82 ; extrusion absolue")
    w("G92 E0")
    if p.purge == "interne" or (p.purge and not klipper):
        w("; ligne de purge")
        x0 = max(mn[0] - 8, 2.0)
        w.deplacer([x0, max(mn[1], 2.0), 0.3])
        w.extruder(np.array([[x0, max(mn[1], 2.0), 0.3], [x0, min(mx[1], p.plateau[1] - 2), 0.3]]),
                   p.vitesse_premiere_couche, "purge", deplacer=False)
        w._retracter()
    elif p.purge:
        w(p.purge)                       # macro KAMP : LINE_PURGE, VORON_PURGE…
        w("G90")
        w("M82")
        w("G92 E0")

    # -- couches ---------------------------------------------------------------
    plusieurs = len(pieces) > 1
    debut_spirale = max(p.couches_fond, 1)   # la 1re couche est toujours à plat
    for k in range(nb_couches):
        z = h * (k + 1)
        w(";LAYER_CHANGE")
        w(f";Z:{z:.3f}")
        w(f";HEIGHT:{h}")
        w(";BEFORE_LAYER_CHANGE")
        w(f";{z:.3f}")
        if klipper:
            w(f"SET_PRINT_STATS_INFO CURRENT_LAYER={k + 1}")
        if k == 1 and p.ventilateur:
            w(f"M106 S{p.ventilateur}")
        v = p.vitesse_premiere_couche if k == 0 else p.vitesse
        for n, q in zip(noms, pieces):
            if q.z[-1] < z - 1e-6:
                continue
            if objets:
                w(f"EXCLUDE_OBJECT_START NAME={n}")
            if mode == "spirale" and k >= debut_spirale:
                c0 = q.contour_a(z - h)
                c1 = q.contour_a(z)
                N = len(c0)
                a = (np.arange(1, N + 1) / N)[:, None]
                xy = c0 + (c1 - c0) * a
                pts = np.column_stack([xy, z - h + h * a[:, 0]])
                if k == debut_spirale:
                    w.extruder(np.vstack([[*c0[0], z - h], pts]), v, "spirale")
                else:
                    w.extruder(pts, v, "spirale", deplacer=False)
            else:
                c = q.contour_a(z)
                if q.fond and k < p.couches_fond:
                    _fond(w, c, z, k, v)
                else:
                    w.extruder(_ferme(c, z), v, "perimetre")
            if objets:
                # chaque objet se termine rétracté : si Klipper en saute un,
                # l'état du filament reste cohérent pour le suivant
                if plusieurs:
                    w._retracter()
                w(f"EXCLUDE_OBJECT_END NAME={n}")

    # -- fin -----------------------------------------------------------------------
    w._retracter()
    if klipper and p.macro_fin:
        w(p.macro_fin.format(**vars(p)))
    else:
        w("G91")
        w("G1 Z10 F600")
        w("G90")
        w(f"G0 X{min(10.0, p.plateau[0]):.1f} Y{p.plateau[1] - 10:.1f} F{p.vitesse_deplacement * 60:.0f}")
        w("M104 S0")
        w("M140 S0")
        w("M107")
        w("M84")

    volume_cm3 = w.filament * np.pi * (p.diametre_filament / 2) ** 2 / 1000
    masse = volume_cm3 * p.densite_g_cm3
    duree_s = w.temps * 1.15   # +15 % pour les accélérations

    # -- métadonnées (format PrusaSlicer, lu par Moonraker en fin de fichier) ----
    w("")
    w(f"; filament used [mm] = {w.filament:.2f}")
    w(f"; filament used [cm3] = {volume_cm3:.2f}")
    w(f"; filament used [g] = {masse:.2f}")
    w(f"; total filament used [g] = {masse:.2f}")
    w(f"; estimated printing time (normal mode) = {_duree_texte(duree_s)}")
    w(f"; total layers count = {nb_couches}")
    w(f"; max_z_height = {nb_couches * h:.3f}")
    w("")
    w("; generateur_formes_config = begin")
    meta = {
        "layer_height": h, "first_layer_height": h, "nozzle_diameter": p.diametre_buse,
        "filament_diameter": p.diametre_filament, "filament_density": p.densite_g_cm3,
        "filament_type": p.filament_type, "filament_settings_id": f'"{p.filament_nom}"',
        "filament_colour": p.filament_couleur, "extruder_colour": p.filament_couleur,
        "temperature": p.temp_buse, "first_layer_temperature": p.temp_buse,
        "bed_temperature": p.temp_plateau, "first_layer_bed_temperature": p.temp_plateau,
        "spiral_vase": int(mode == "spirale"), "extrusion_width": p.largeur_ligne,
        "bed_shape": f"0x0,{p.plateau[0]:g}x0,{p.plateau[0]:g}x{p.plateau[1]:g},0x{p.plateau[1]:g}",
        "max_print_height": p.hauteur_max, "gcode_flavor": p.firmware,
    }
    for cle, val in meta.items():
        w(f"; {cle} = {val}")
    w("; generateur_formes_config = end")

    w.trajet.stats = {
        "mode": mode,
        "firmware": p.firmware,
        "pieces": len(pieces),
        "objets": noms if objets else [],
        "couches": nb_couches,
        "filament_m": round(float(w.filament) / 1000, 2),
        "masse_g": round(float(masse), 1),
        "duree_min": int(round(duree_s / 60)),
        "lignes": len(w.lignes),
        "boite_mm": [round(float(x), 1) for x in (*mn, *mx)],
    }
    return "\n".join(w.lignes) + "\n", w.trajet


def exporter_gcode(assemblage, chemin, p: ParametresImpression | None = None) -> Trajet:
    chemin = Path(chemin)
    texte, trajet = generer_gcode(assemblage, p, nom=chemin.stem)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    return trajet
