"""Plaques de test : réglages d'un filament (pensé pour le PETG transparent Arianeplast).

Chaque plaque (35 × 70 mm par défaut) est imprimée pleine, en lignes parallèles,
avec ses propres réglages : température de buse, débit, vitesse, ventilation,
hauteur de couche, largeur de ligne, orientation des lignes. Ses réglages sont
gravés en **empreinte** dans le bas de la plaque (bande du bord avant, y faible) :

- ``face="dessous"`` (par défaut) : en creux dans les premières couches, côté
  plateau. Sur un filament transparent, on la lit à travers la plaque, à
  l'endroit, vue de dessus ; la face du dessus reste lisse pour juger la clarté.
- ``face="dessus"`` : en creux dans les dernières couches.

Les plaques s'impriment **l'une après l'autre** (impression séquentielle) : la
buse change de température entre deux plaques (ordre croissant pour ne pas
attendre le refroidissement), ce qu'une impression couche par couche ne permet
pas. Les plaques étant fines, la tête passe au-dessus des plaques terminées.

Étiquette (lettres gravées) ::

    #3      numéro de la plaque          T245   buse (°C)
    D105    débit (%)                    V25    vitesse (mm/s)
    F20     ventilateur (%)              H20    couche (1/100 mm : 0,20)
    L45     largeur de ligne (1/100 mm)  ML / MT / MX : lignes longitudinales,
                                                transversales, croisées

Utilisation ::

    from formes.plaques import *
    plan = serie("temp_buse", [235, 240, 245, 250, 255])     # ou plan(...), SERIES[...]
    exporter_plaques(plan, "sorties/petg_temp.gcode", ParametresImpression(**PETG_ARIANEPLAST))
"""

from __future__ import annotations

import csv
import itertools
import struct
from dataclasses import dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path

import numpy as np

from .gcode import (VERSION, ParametresImpression, Trajet, _apres_premiere_couche, _demarrer, _Ecrivain,
                    _nom_objet, _polygone_objet, _terminer)
from .geometrie import Forme

# ---------------------------------------------------------------------------
# Préréglages
# ---------------------------------------------------------------------------

# Réglages machine / filament communs à toutes les plaques (ParametresImpression).
# PETG Arianeplast : buse 230–250 °C, plateau 70–80 °C ; vérifiez sur l'étiquette
# de votre bobine.
PETG_ARIANEPLAST = dict(
    filament_type="PETG", filament_nom="PETG transparent Arianeplast", filament_couleur="#DDEEF2",
    temp_buse=245, temp_plateau=75, densite_g_cm3=1.27, retraction=1.0, vitesse_retraction=30.0,
    vitesse_premiere_couche=15.0, vitesse_deplacement=150.0,
)



MOTIFS = ("longitudinal", "transversal", "croise")
CODES_MOTIF = {"longitudinal": "ML", "transversal": "MT", "croise": "MX"}


@dataclass
class ReglagePlaque:
    """Réglages propres à une plaque (ce que l'on évalue)."""

    temp_buse: int = 245
    flux: float = 1.05                 # multiplicateur de débit
    vitesse: float = 25.0              # mm/s (lignes et périmètres, couches > 1)
    ventilateur: int = 20              # % (à partir de la 2e couche)
    hauteur_couche: float = 0.20
    largeur_ligne: float = 0.45
    motif: str = "longitudinal"        # lignes : longitudinal | transversal | croise

    def etiquette(self, numero: int | None = None, champs=None) -> list[str]:
        """Mots gravés sur la plaque."""
        champs = champs or CHAMPS_DEFAUT
        mots = {
            "numero": f"#{numero}" if numero is not None else "",
            "temp_buse": f"T{self.temp_buse:d}",
            "flux": f"D{round(self.flux * 100):d}",
            "vitesse": f"V{self.vitesse:g}",
            "ventilateur": f"F{self.ventilateur:d}",
            "hauteur_couche": f"H{round(self.hauteur_couche * 100):02d}",
            "largeur_ligne": f"L{round(self.largeur_ligne * 100):d}",
            "motif": CODES_MOTIF.get(self.motif, "M?"),
        }
        return [mots[c] for c in champs if mots.get(c)]


# Base recommandée pour la transparence : chaud, lent, débit légèrement élevé,
# peu de ventilation, lignes toutes dans le même sens.
REGLAGE_TRANSPARENT = ReglagePlaque()

CHAMPS_DEFAUT = ("numero", "temp_buse", "flux", "vitesse", "ventilateur", "hauteur_couche")

LEGENDE = {
    "#": "numéro de plaque", "T": "température buse (°C)", "D": "débit (%)",
    "V": "vitesse (mm/s)", "F": "ventilateur (%)", "H": "hauteur de couche (1/100 mm)",
    "L": "largeur de ligne (1/100 mm)",
    "M": "lignes : ML longitudinales, MT transversales, MX croisées",
}

# Séries prêtes à l'emploi : paramètre → valeurs
SERIES = {
    "Température buse": ("temp_buse", [230, 235, 240, 245, 250, 255, 260]),
    "Débit": ("flux", [0.98, 1.00, 1.02, 1.04, 1.06, 1.08, 1.10, 1.12]),
    "Vitesse": ("vitesse", [15, 20, 25, 30, 40, 50]),
    "Ventilateur": ("ventilateur", [0, 10, 20, 30, 50, 80]),
    "Hauteur de couche": ("hauteur_couche", [0.12, 0.16, 0.20, 0.24, 0.28]),
    "Largeur de ligne": ("largeur_ligne", [0.40, 0.45, 0.50, 0.55, 0.60]),
    "Orientation des lignes": ("motif", list(MOTIFS)),
}


@dataclass
class Plaques:
    """Géométrie commune et liste des réglages à tester (une plaque par réglage)."""

    reglages: list = field(default_factory=lambda: [ReglagePlaque()])
    largeur: float = 35.0              # X (mm)
    longueur: float = 70.0             # Y (mm)
    epaisseur: float = 2.0             # mm (arrondie à un nombre entier de couches)
    perimetres: int = 1
    face: str = "dessous"              # empreinte : dessous | dessus | aucune
    profondeur: float = 0.8            # profondeur de l'empreinte (mm)
    taille_pixel: float = 0.9          # pas de la police (mm), calé sur la largeur de ligne
    marge_texte: float = 2.0           # distance entre le texte et le bord (mm)
    # None : numéro + paramètres qui changent d'une plaque à l'autre (le reste est dans la fiche)
    champs: tuple | None = None
    police: str = "auto"               # auto (la plus grande qui tient) | 5x7 | 3x5
    hauteur_texte_max: float = 0.4     # part de la longueur occupée au plus par le texte (police auto)
    contour_lettres: bool = True       # périmètre autour de chaque lettre : bords nets
    lecture: str = "travers"           # travers (vue de dessus, à travers la plaque) | plateau (miroir)
    ecart: float = 8.0                 # espace entre deux plaques sur le plateau (mm)
    marge_plateau: float = 10.0
    trier_temperature: bool = True     # impression par température croissante
    amorce: bool = True                # ligne d'amorçage avant chaque plaque après une chauffe
    degagement_tete: float = 3.0       # hauteur libre sous la tête autour de la buse (mm)
    z_hop: float = 0.4                 # levée minimale de la buse pendant les déplacements rétractés (mm)

    def __post_init__(self):
        self.reglages = [r if isinstance(r, ReglagePlaque) else ReglagePlaque(**r) for r in self.reglages]


def plan(base: ReglagePlaque | None = None, **variations) -> Plaques:
    """Toutes les combinaisons des ``variations`` autour de ``base``.

    ``plan(temp_buse=[240, 250], flux=[1.0, 1.05])`` → 4 plaques.
    """
    base = base or REGLAGE_TRANSPARENT
    for nom in variations:
        if nom not in {f.name for f in fields(ReglagePlaque)}:
            raise ValueError(f"paramètre inconnu : {nom!r}")
    noms = list(variations)
    combos = itertools.product(*(variations[n] for n in noms)) if noms else [()]
    return Plaques([replace(base, **dict(zip(noms, c))) for c in combos])


def serie(parametre: str, valeurs, base: ReglagePlaque | None = None, **kw) -> Plaques:
    """Une plaque par valeur d'un seul paramètre."""
    p = plan(base, **{parametre: list(valeurs)})
    return replace(p, **kw) if kw else p


# ---------------------------------------------------------------------------
# Police 3 × 5 (pixels), lignes du haut vers le bas
# ---------------------------------------------------------------------------

POLICE = {
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", "..#", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
    "A": [".#.", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"], "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"], "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"], "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"], "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#.#", "###", "###", "#.#", "#.#"], "N": ["##.", "#.#", "#.#", "#.#", "#.#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."], "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "##.", ".##"], "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."], "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"], "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#.#", "#.#", "###", "###", "#.#"], "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."], "Z": ["###", "..#", ".#.", "#..", "###"],
    ".": ["...", "...", "...", "...", ".#."], ",": ["...", "...", "...", ".#.", "#.."],
    "-": ["...", "...", "###", "...", "..."], "+": ["...", ".#.", "###", ".#.", "..."],
    "#": ["#.#", "###", "#.#", "###", "#.#"], "%": ["#.#", "..#", ".#.", "#..", "#.#"],
    "/": ["..#", "..#", ".#.", "#..", "#.."], ":": ["...", ".#.", "...", ".#.", "..."],
    "=": ["...", "###", "...", "###", "..."], " ": ["...", "...", "...", "...", "..."],
}


POLICE_5X7 = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["###..", "#..#.", "#...#", "#...#", "#...#", "#..#.", "###.."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    ",": [".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    "#": [".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."],
    "%": ["##...", "##..#", "...#.", "..#..", ".#...", "#..##", "...##"],
    "/": [".....", "....#", "...#.", "..#..", ".#...", "#....", "....."],
    ":": [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    "=": [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
}

# nom → (glyphes, largeur, hauteur) ; « auto » essaie la plus grande d'abord
POLICES = {"5x7": (POLICE_5X7, 5, 7), "3x5": (POLICE, 3, 5)}


def _couper(mots: list[str], max_car: int) -> list[str]:
    """Regroupe les mots en lignes d'au plus ``max_car`` caractères."""
    lignes, courante = [], ""
    for m in mots:
        essai = f"{courante} {m}" if courante else m
        if len(essai) <= max_car or not courante:
            courante = essai
        else:
            lignes.append(courante)
            courante = m
    return lignes + [courante] * bool(courante)


def texte_pixels(lignes: list[str], police: str = "3x5", miroir: bool = False) -> np.ndarray:
    """Masque booléen (rangées, colonnes) ; rangée 0 = haut du texte.

    ``miroir`` : texte retourné gauche-droite, lisible depuis la face posée sur le plateau.
    """
    glyphes, gl, gh = POLICES[police]
    pas_c, pas_r = gl + 1, gh + 2                  # 1 colonne entre les lettres, 2 rangées entre les lignes
    larg = max(len(l) for l in lignes) * pas_c - 1
    img = np.zeros((len(lignes) * pas_r - 2, larg), bool)
    for i, ligne in enumerate(lignes):
        x0 = (larg - (len(ligne) * pas_c - 1)) // 2      # lignes centrées
        for j, c in enumerate(ligne.upper()):
            g = glyphes.get(c, glyphes[" "])
            for r, rangee in enumerate(g):
                for k, px in enumerate(rangee):
                    if px == "#":
                        img[i * pas_r + r, x0 + j * pas_c + k] = True
    return img[:, ::-1] if miroir else img


def champs_effectifs(cfg: "Plaques") -> tuple:
    """Champs gravés : ceux demandés, sinon le numéro et les paramètres qui varient."""
    if cfg.champs:
        return tuple(cfg.champs)
    ordre = ("temp_buse", "flux", "vitesse", "ventilateur", "hauteur_couche", "largeur_ligne", "motif")
    varies = [c for c in ordre if len({getattr(r, c) for r in cfg.reglages}) > 1]
    return ("numero", *varies) if varies else CHAMPS_DEFAUT


def _contours(img: np.ndarray, x0: float, y0: float, px: float, decalage: float) -> list[np.ndarray]:
    """Boucles (N, 2) qui entourent les creux du masque, décalées de ``decalage`` dans la matière.

    Les bords des pixels sont parcourus creux à gauche ; aux contacts en diagonale, la boucle
    tourne à droite (chaque creux garde sa boucle). Rangée 0 du masque = haut (y max).
    """
    rangees, colonnes = img.shape
    creux = lambda c, r: 0 <= c < colonnes and 0 <= r < rangees and img[rangees - 1 - r, c]
    aretes = {}
    for r in range(rangees):
        for c in range(colonnes):
            if not creux(c, r):
                continue
            if not creux(c, r - 1):
                aretes.setdefault((c, r), []).append((c + 1, r))
            if not creux(c + 1, r):
                aretes.setdefault((c + 1, r), []).append((c + 1, r + 1))
            if not creux(c, r + 1):
                aretes.setdefault((c + 1, r + 1), []).append((c, r + 1))
            if not creux(c - 1, r):
                aretes.setdefault((c, r + 1), []).append((c, r))
    boucles = []
    while aretes:
        depart = next(iter(aretes))
        chemin, a, sens = [], depart, None
        while True:
            chemin.append(a)
            suivants = aretes[a]
            b = suivants[0]
            if len(suivants) > 1 and sens is not None:   # contact en diagonale : à droite d'abord
                droite = (a[0] + sens[1], a[1] - sens[0])
                b = droite if droite in suivants else b
            suivants.remove(b)
            if not suivants:
                del aretes[a]
            sens = (b[0] - a[0], b[1] - a[1])
            a = b
            if a == depart:
                break
        pts = np.array(chemin, float)
        # sommets utiles (changements de direction)
        n = len(pts)

        def tourne(i):
            u, v = pts[i] - pts[i - 1], pts[(i + 1) % n] - pts[i]
            return u[0] * v[1] - u[1] * v[0] != 0

        garde = [i for i in range(n) if tourne(i)]
        pts = pts[garde]
        n = len(pts)
        sortie = []
        for i in range(n):
            a_, b_ = pts[i] - pts[i - 1], pts[(i + 1) % n] - pts[i]
            na = np.array([a_[1], -a_[0]]) / np.linalg.norm(a_)          # normale à droite : matière
            nb = np.array([b_[1], -b_[0]]) / np.linalg.norm(b_)
            sortie.append(pts[i] * px + [x0, y0] + decalage * (na + nb))
        boucles.append(np.array(sortie))
    return boucles


# ---------------------------------------------------------------------------
# Géométrie d'une plaque
# ---------------------------------------------------------------------------

@dataclass
class Plaque:
    """Une plaque placée sur le plateau, prête à trancher."""

    numero: int
    reglage: ReglagePlaque
    origine: np.ndarray                # coin avant gauche (x, y)
    largeur: float
    longueur: float
    couches: int
    couches_empreinte: int
    face: str
    trous: list                        # rectangles (x0, x1, y0, y1) de l'empreinte, en local
    lignes_texte: list
    perimetres: int
    contours: list = field(default_factory=list)   # boucles autour des lettres (centres du cordon)

    @property
    def epaisseur(self) -> float:
        return self.couches * self.reglage.hauteur_couche

    @property
    def profondeur(self) -> float:
        return self.couches_empreinte * self.reglage.hauteur_couche

    def grave(self, k: int) -> bool:
        """La couche ``k`` (0 = première) porte-t-elle l'empreinte ?"""
        if self.face == "dessous":
            return k < self.couches_empreinte
        if self.face == "dessus":
            return k >= self.couches - self.couches_empreinte
        return False

    def forme(self, points_par_cote: int = 8) -> Forme:
        """Pavé de la plaque (vignettes, objets Klipper, vue 3D)."""
        x0, y0 = self.origine
        x1, y1 = x0 + self.largeur, y0 + self.longueur
        t = np.linspace(0, 1, points_par_cote, endpoint=False)
        bord = np.concatenate([
            np.column_stack([x0 + t * (x1 - x0), np.full_like(t, y0)]),
            np.column_stack([np.full_like(t, x1), y0 + t * (y1 - y0)]),
            np.column_stack([x1 - t * (x1 - x0), np.full_like(t, y1)]),
            np.column_stack([np.full_like(t, x0), y1 - t * (y1 - y0)]),
        ])
        pts = np.stack([np.column_stack([bord, np.full(len(bord), z)]) for z in (0.0, self.epaisseur)])
        return Forme(pts, nom=f"plaque_{self.numero}", fond=True, ferme_haut=True)

    def maillage(self):
        """(sommets, triangles) de la plaque avec son empreinte, en coordonnées plateau."""
        xs = np.unique(np.r_[0.0, self.largeur, [t[0] for t in self.trous], [t[1] for t in self.trous]])
        ys = np.unique(np.r_[0.0, self.longueur, [t[2] for t in self.trous], [t[3] for t in self.trous]])
        nx, ny = len(xs) - 1, len(ys) - 1
        creux = np.zeros((nx, ny), bool)
        cx, cy = (xs[:-1] + xs[1:]) / 2, (ys[:-1] + ys[1:]) / 2
        for x0, x1, y0, y1 in self.trous:
            creux[np.ix_((cx > x0) & (cx < x1), (cy > y0) & (cy < y1))] = True
        e, d = self.epaisseur, self.profondeur
        bas = np.where(creux & (self.face == "dessous"), d, 0.0)
        haut = np.where(creux & (self.face == "dessus"), e - d, e)
        tris = []

        def quad(a, b, c, dd):
            tris.extend([(a, b, c), (a, c, dd)])

        for i in range(nx):
            for j in range(ny):
                x0, x1, y0, y1 = xs[i], xs[i + 1], ys[j], ys[j + 1]
                zb, zh = bas[i, j], haut[i, j]
                quad((x0, y0, zh), (x1, y0, zh), (x1, y1, zh), (x0, y1, zh))
                quad((x0, y0, zb), (x0, y1, zb), (x1, y1, zb), (x1, y0, zb))
                # parois vers +x et +y : partie de la cellule non couverte par la voisine
                for di, dj in ((1, 0), (0, 1)):
                    ii, jj = i + di, j + dj
                    voisin = (bas[ii, jj], haut[ii, jj]) if ii < nx and jj < ny else None
                    for za, zc in _difference((zb, zh), voisin):
                        if di:
                            quad((x1, y0, za), (x1, y1, za), (x1, y1, zc), (x1, y0, zc))
                        else:
                            quad((x1, y1, za), (x0, y1, za), (x0, y1, zc), (x1, y1, zc))
                    if voisin:                       # partie de la voisine qui nous fait face
                        for za, zc in _difference(voisin, (zb, zh)):
                            if di:
                                quad((x1, y1, za), (x1, y0, za), (x1, y0, zc), (x1, y1, zc))
                            else:
                                quad((x0, y1, za), (x1, y1, za), (x1, y1, zc), (x0, y1, zc))
                # bords -x et -y de la plaque
                if i == 0:
                    quad((x0, y1, zb), (x0, y0, zb), (x0, y0, zh), (x0, y1, zh))
                if j == 0:
                    quad((x0, y0, zb), (x1, y0, zb), (x1, y0, zh), (x0, y0, zh))
        v, f = np.unique(np.asarray(tris, float).reshape(-1, 3), axis=0, return_inverse=True)
        v[:, :2] += self.origine
        return v, f.reshape(-1, 3)


def _difference(a, b):
    """Intervalle ``a`` privé de ``b`` (liste de 0 à 2 intervalles)."""
    if b is None or b[1] <= a[0] or b[0] >= a[1]:
        return [a]
    res = []
    if b[0] > a[0] + 1e-9:
        res.append((a[0], b[0]))
    if b[1] < a[1] - 1e-9:
        res.append((b[1], a[1]))
    return res


def _empreinte(cfg: Plaques, r: ReglagePlaque, numero: int, av: list, champs=None):
    """Creux de l'empreinte, calés sur la grille des lignes.

    Renvoie (rectangles (x0, x1, y0, y1), lignes de texte, contours des lettres), en
    coordonnées locales. Le pas du pixel est un multiple entier de la largeur de ligne et
    les bords des pixels tombent entre deux lignes : chaque pixel retire exactement des
    lignes entières, quel que soit le sens des lignes.
    """
    lw = r.largeur_ligne
    n = max(2, round(cfg.taille_pixel / lw))
    px = n * lw
    debut = cfg.perimetres * lw                    # bord de la zone de remplissage
    marge = max(cfg.marge_texte, debut + lw + (lw if cfg.contour_lettres else 0))
    mots = r.etiquette(numero, champs or champs_effectifs(cfg))
    if not mots or cfg.face == "aucune":
        return [], [], []
    if cfg.police not in ("auto", *POLICES):
        raise ValueError(f"police inconnue : {cfg.police!r} (auto | {' | '.join(POLICES)})")
    max_col = int((cfg.largeur - 2 * marge) / px)
    for police in (POLICES if cfg.police == "auto" else [cfg.police]):
        gl, gh = POLICES[police][1:]
        max_car = max((max_col + 1) // (gl + 1), 1)
        lignes = _couper(mots, max_car)
        hauteur = (len(lignes) * (gh + 2) - 2) * px
        if all(len(l) <= max_car for l in lignes) and hauteur <= cfg.hauteur_texte_max * cfg.longueur:
            break
    trop = [l for l in lignes if len(l) > max_car]
    if trop:
        av.append(f"plaque {numero} : « {trop[0]} » trop large pour la plaque, "
                  "réduisez la taille du texte ou le nombre de champs")
    miroir = cfg.lecture == "plateau" and cfg.face == "dessous"
    img = texte_pixels(lignes, police, miroir)
    rangees, colonnes = img.shape
    if rangees * px > cfg.longueur / 2:
        av.append(f"plaque {numero} : le texte occupe plus de la moitié de la plaque")

    def caler(v):                                  # bord de pixel entre deux lignes
        return debut + round((v - debut) / lw) * lw

    x0 = caler((cfg.largeur - colonnes * px) / 2)
    y0 = caler(marge)
    trous = []
    for i in range(rangees):
        y_haut = y0 + (rangees - i) * px           # rangée 0 en haut
        j = 0
        while j < colonnes:
            if img[i, j]:
                k = j
                while k < colonnes and img[i, k]:
                    k += 1
                trous.append(tuple(round(float(c), 6) for c in
                                   (x0 + j * px, x0 + k * px, y_haut - px, y_haut)))
                j = k
            else:
                j += 1
    contours = _contours(img, x0, y0, px, lw / 2) if cfg.contour_lettres else []
    return trous, lignes, [np.round(c, 6) for c in contours]


def disposer(cfg: Plaques, p: ParametresImpression,
             numeros: list[int] | None = None) -> tuple[list[list[Plaque]], list[str]]:
    """Place les plaques sur le plateau ; renvoie des lots (un G-code par lot) et des alertes.

    ``numeros`` : numéros gravés (par défaut 1, 2, 3… dans l'ordre de ``cfg.reglages``).
    """
    numeros = numeros or list(range(1, len(cfg.reglages) + 1))
    champs = champs_effectifs(cfg)
    if cfg.lecture not in ("travers", "plateau"):
        raise ValueError(f"lecture inconnue : {cfg.lecture!r} (travers | plateau)")
    av: list[str] = []
    if cfg.face not in ("dessous", "dessus", "aucune"):
        raise ValueError(f"face inconnue : {cfg.face!r} (dessous | dessus | aucune)")
    for r in cfg.reglages:
        if r.motif not in MOTIFS:
            raise ValueError(f"motif inconnu : {r.motif!r} ({' | '.join(MOTIFS)})")
    ordre = list(range(len(cfg.reglages)))
    if cfg.trier_temperature:
        ordre.sort(key=lambda i: cfg.reglages[i].temp_buse)
    pas_x, pas_y = cfg.largeur + cfg.ecart, cfg.longueur + cfg.ecart
    cols = max(int((p.plateau[0] - 2 * cfg.marge_plateau + cfg.ecart) // pas_x), 1)
    rangs = max(int((p.plateau[1] - 2 * cfg.marge_plateau + cfg.ecart) // pas_y), 1)
    par_lot = cols * rangs
    if cols * pas_x - cfg.ecart > p.plateau[0] or rangs * pas_y - cfg.ecart > p.plateau[1]:
        av.append("plaque plus grande que le plateau")
    lots = []
    for debut in range(0, len(ordre), par_lot):
        indices = ordre[debut:debut + par_lot]
        c = min(cols, len(indices))
        lignes = int(np.ceil(len(indices) / c))
        larg, prof = c * pas_x - cfg.ecart, lignes * pas_y - cfg.ecart
        ox = (p.plateau[0] - larg) / 2
        oy = (p.plateau[1] - prof) / 2
        lot = []
        for k, i in enumerate(indices):
            r = cfg.reglages[i]
            ligne, col = divmod(k, c)
            # de l'arrière vers l'avant : la tête s'éloigne des plaques déjà faites
            origine = np.array([ox + col * pas_x, oy + (lignes - 1 - ligne) * pas_y])
            trous, texte, contours = _empreinte(cfg, r, numeros[i], av, champs)
            couches = max(int(round(cfg.epaisseur / r.hauteur_couche)), 2)
            emp = min(max(int(round(cfg.profondeur / r.hauteur_couche)), 1), couches - 1)
            lot.append(Plaque(numeros[i], r, origine, cfg.largeur, cfg.longueur, couches, emp,
                              cfg.face, trous, texte, cfg.perimetres, contours))
        lots.append(lot)
    if len(lots) > 1:
        av.append(f"{len(cfg.reglages)} plaques : {len(lots)} lots de {par_lot} maximum "
                  "(un G-code par lot)")
    epaisseur = max(q.epaisseur for lot in lots for q in lot)
    if epaisseur > cfg.degagement_tete:
        av.append(f"plaques de {epaisseur:.1f} mm : la tête (dégagement {cfg.degagement_tete:.1f} mm) "
                  "peut accrocher les plaques déjà imprimées ; plaques plus fines ou un fichier par plaque")
    return lots, av


# ---------------------------------------------------------------------------
# Trajets
# ---------------------------------------------------------------------------

def _segments_ligne(position: float, debut: float, fin: float, trous, axe: int, lw: float,
                    contour: bool = False):
    """Morceaux d'une ligne (le long de l'axe ``axe``) privés des trous de l'empreinte.

    ``contour`` : un périmètre longe déjà chaque lettre ; la ligne laisse sa place (une largeur
    de ligne autour du creux) et s'arrête contre lui avec le recouvrement habituel.
    """
    marge = lw if contour else 0.0                      # bande du contour, de part et d'autre
    bout = (1.35 * lw) if contour else lw / 2           # le cordon s'arrête au bord du creux / du contour
    coupes = []
    for x0, x1, y0, y1 in trous:
        a0, a1, b0, b1 = (y0, y1, x0, x1) if axe == 1 else (x0, x1, y0, y1)
        if b0 - marge < position < b1 + marge:
            coupes.append((a0 - bout, a1 + bout))
    coupes.sort()
    morceaux, cur = [], debut
    for c0, c1 in coupes:
        if c0 > cur:
            morceaux.append((cur, min(c0, fin)))
        cur = max(cur, c1)
    if cur < fin:
        morceaux.append((cur, fin))
    return [(a, b) for a, b in morceaux if b - a > 0.2]


def _couche(w: _Ecrivain, q: Plaque, k: int, z: float, v: float):
    """Une couche : périmètres puis lignes en zigzag.

    La couche commence au coin le plus proche de la buse (là où la précédente s'est
    terminée) : pas de traversée de la plaque juste au-dessus de la surface imprimée.
    """
    r = q.reglage
    lw = r.largeur_ligne
    ox, oy = q.origine
    ici = w.pos[:2] - q.origine                     # position de la buse, en local
    d = q.perimetres * lw                           # bord intérieur des périmètres
    # coin de départ : 0/1 = côté x bas/haut, 0/1 = côté y bas/haut
    cx = int(ici[0] > q.largeur / 2)
    cy = int(ici[1] > q.longueur / 2)
    for i in range(q.perimetres):
        e = lw / 2 + i * lw
        x0, y0, x1, y1 = ox + e, oy + e, ox + q.largeur - e, oy + q.longueur - e
        coins = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        depart = {(0, 0): 0, (1, 0): 1, (1, 1): 2, (0, 1): 3}[(cx, cy)]
        coins = coins[depart:] + coins[:depart]
        w.extruder(np.array([[*c, z] for c in coins + coins[:1]]), v, "perimetre")
    # contour des lettres (couches gravées) : bords nets, pas de bouts de lignes dans les creux
    contours = q.contours if q.grave(k) else []
    restants = [c + q.origine for c in contours]
    while restants:
        i = min(range(len(restants)), key=lambda i: np.linalg.norm(restants[i] - w.pos[:2], axis=1).min())
        boucle = restants.pop(i)
        j = int(np.argmin(np.linalg.norm(boucle - w.pos[:2], axis=1)))
        boucle = np.roll(boucle, -j, axis=0)
        w.extruder(np.column_stack([np.vstack([boucle, boucle[:1]]), np.full(len(boucle) + 1, z)]),
                   v, "perimetre")
    # remplissage plein, lignes parallèles en zigzag ; les centres des lignes tombent
    # au milieu des pixels de l'empreinte (voir _empreinte)
    if contours:                                    # repartir du coin le plus proche des lettres
        ici = w.pos[:2] - q.origine
        cx, cy = int(ici[0] > q.largeur / 2), int(ici[1] > q.longueur / 2)
    recouvrement = 0.15 * lw if q.perimetres else 0.0
    long = r.motif == "longitudinal" or (r.motif == "croise" and k % 2 == 0)
    axe = 1 if long else 0                          # axe le long duquel court la ligne
    trous = q.trous if q.grave(k) else []
    taille = (q.largeur, q.longueur)
    a_debut = d + lw / 2 - recouvrement
    a_fin = taille[axe] - d - lw / 2 + recouvrement
    positions = np.arange(d + lw / 2, taille[1 - axe] - d - lw / 2 + 1e-6, lw)
    coin = (cx, cy)
    if coin[1 - axe]:                               # première ligne du côté du coin de départ
        positions = positions[::-1]
    sens_initial = coin[axe]                        # 1 : la première ligne part du côté haut
    for n, pos in enumerate(positions):
        morceaux = _segments_ligne(pos, a_debut, a_fin, trous, axe, lw, contour=bool(contours))
        if (n + sens_initial) % 2:
            morceaux = [(b, a) for a, b in reversed(morceaux)]
        for a, b in morceaux:
            if axe == 1:
                seg = np.array([[ox + pos, oy + a, z], [ox + pos, oy + b, z]])
            else:
                seg = np.array([[ox + a, oy + pos, z], [ox + b, oy + pos, z]])
            proche = np.linalg.norm(seg[0, :2] - w.pos[:2]) < 1.5 * lw
            w.extruder(seg, v, "remplissage", deplacer=not proche)


def _e_par_mm(p: ParametresImpression, r: ReglagePlaque) -> float:
    section = np.pi * (p.diametre_filament / 2) ** 2
    return r.largeur_ligne * r.hauteur_couche * r.flux / section


def generer_gcode_plaques(lot: list[Plaque], cfg: Plaques, p: ParametresImpression | None = None,
                          nom: str = "plaques"):
    """G-code d'un lot de plaques imprimées l'une après l'autre. Renvoie (texte, Trajet)."""
    p = p or ParametresImpression(**PETG_ARIANEPLAST)
    if p.firmware not in ("klipper", "marlin"):
        raise ValueError(f"firmware inconnu : {p.firmware!r} (klipper | marlin)")
    klipper = p.firmware == "klipper"
    premier = lot[0].reglage
    # la température et la hauteur de couche sont celles de chaque plaque (ce que l'on teste) :
    # pas de valeurs propres à la 1re couche, sauf pour le plateau
    p = replace(p, temp_buse=premier.temp_buse, hauteur_couche=premier.hauteur_couche,
                largeur_ligne=premier.largeur_ligne, mode="couches",
                temp_buse_premiere_couche=None, hauteur_premiere_couche=None,
                z_hop=max(p.z_hop, cfg.z_hop))
    w = _Ecrivain(p)
    av = w.trajet.avertissements
    formes = [q.forme() for q in lot]
    mn = np.min([f.boite()[0] for f in formes], 0)
    mx = np.max([f.boite()[1] for f in formes], 0)
    if mn[0] < 0 or mn[1] < 0 or mx[0] > p.plateau[0] or mx[1] > p.plateau[1]:
        av.append("les plaques dépassent du plateau")
    nb_couches = sum(q.couches for q in lot)
    objets = klipper and p.exclude_object
    noms = [_nom_objet(f"plaque_{q.numero}", q.numero) for q in lot]

    w(f"; generated by generateur-formes {VERSION} on {datetime.now():%Y-%m-%d at %H:%M:%S}")
    w(";")
    if p.vignettes:
        try:
            from .vignettes import vignettes_gcode
            for ligne in vignettes_gcode(formes, p.vignettes):
                w(ligne)
            w(";")
        except ImportError:
            av.append("matplotlib absent : G-code généré sans vignette d'aperçu")
    w(f"; {nom} - plaques de test {p.filament_nom}, impression sequentielle, firmware {p.firmware}")
    w(f"; {len(lot)} plaque(s) {cfg.largeur:g} x {cfg.longueur:g} mm, empreinte {cfg.face}")
    for q in lot:
        r = q.reglage
        w(f"; plaque {q.numero} : buse {r.temp_buse} C, debit {r.flux:.2f}, vitesse {r.vitesse:g} mm/s, "
          f"ventilateur {r.ventilateur} %, couche {r.hauteur_couche:.2f} mm, ligne {r.largeur_ligne:.2f} mm, "
          f"lignes {r.motif} | {' / '.join(q.lignes_texte)}")
    w(";")
    if objets:
        for n, f in zip(noms, formes):
            poly = _polygone_objet(f)
            c = f.centres().mean(axis=0)
            pts = ",".join(f"[{x:.3f},{y:.3f}]" for x, y in poly)
            w(f"EXCLUDE_OBJECT_DEFINE NAME={n} CENTER={c[0]:.3f},{c[1]:.3f} POLYGON=[{pts}]")
    if klipper:
        w(f"SET_PRINT_STATS_INFO TOTAL_LAYER={nb_couches}")

    _demarrer(w, mn, mx)

    temp = premier.temp_buse
    z_sur = 0.0                                     # plus haute plaque déjà imprimée
    couche_globale = 0
    for n, q in zip(noms, lot):
        r = q.reglage
        w.e_par_mm = _e_par_mm(p, r)
        ox, oy = q.origine
        w(f"; ===== plaque {q.numero} =====")
        if objets:
            w(f"EXCLUDE_OBJECT_START NAME={n}")
        w("M107")
        if z_sur > 0:                               # dégagement au-dessus des plaques finies
            w._retracter()
            w.deplacer([w.pos[0], w.pos[1], z_sur + cfg.degagement_tete + 1.0])
            w.deplacer([ox - 3.0, oy + 2.0, z_sur + cfg.degagement_tete + 1.0])
        chauffe = r.temp_buse != temp
        if chauffe:
            w(f"M104 S{r.temp_buse}")
            # Marlin : M109 S n'attend qu'en chauffe, R attend aussi le refroidissement
            w(f"M109 {'R' if (r.temp_buse < temp and not klipper) else 'S'}{r.temp_buse}")
            w.temps += 4 * abs(r.temp_buse - temp)  # ≈ 4 s par degré
            temp = r.temp_buse
        if cfg.amorce and chauffe:
            z0 = min(0.3, r.hauteur_couche * 1.5)
            amorce = np.array([[ox - 3.0, oy + 2.0, z0], [ox - 3.0, oy + min(30.0, q.longueur - 2), z0]])
            w.deplacer(amorce[0])
            w.extruder(amorce, p.vitesse_premiere_couche, "purge", deplacer=False)
        for k in range(q.couches):
            z = r.hauteur_couche * (k + 1)
            couche_globale += 1
            w(";LAYER_CHANGE")
            w(f";Z:{z:.3f}")
            w(f";HEIGHT:{r.hauteur_couche}")
            if klipper:
                w(f"SET_PRINT_STATS_INFO CURRENT_LAYER={couche_globale}")
            if k == 1 and couche_globale == 2:
                _apres_premiere_couche(w)               # plateau des couches suivantes
            if k == p.couches_sans_ventilateur and r.ventilateur:
                w(f"M106 S{round(r.ventilateur * 2.55)}")
            v = min(p.vitesse_premiere_couche, r.vitesse) if k == 0 else r.vitesse
            if k:                                       # monter d'abord, à la verticale
                w.deplacer([w.pos[0], w.pos[1], z])
            _couche(w, q, k, z, v)
        w._retracter()
        z_sur = max(z_sur, q.epaisseur)
        w.deplacer([w.pos[0], w.pos[1], z_sur + 1.0])
        if objets:
            w(f"EXCLUDE_OBJECT_END NAME={n}")

    hauteurs = {q.reglage.hauteur_couche for q in lot}
    masse, duree_s = _terminer(w, nb_couches, z_sur, {
        "layer_height": premier.hauteur_couche if len(hauteurs) == 1 else min(hauteurs),
    })
    w.trajet.stats = {
        "mode": "sequentiel",
        "firmware": p.firmware,
        "pieces": len(lot),
        "objets": noms if objets else [],
        "couches": nb_couches,
        "filament_m": round(float(w.filament) / 1000, 2),
        "masse_g": round(float(masse), 1),
        "cout_eur": round(float(masse) / 1000 * p.cout_kg, 2),
        "duree_min": int(round(duree_s / 60)),
        "lignes": len(w.lignes),
        "boite_mm": [round(float(x), 1) for x in (*mn, *mx)],
    }
    return "\n".join(w.lignes) + "\n", w.trajet


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def _chemins(chemin: Path, n: int, suffixe: str) -> list[Path]:
    if n == 1:
        return [chemin]
    return [chemin.with_name(f"{chemin.stem}_{suffixe}{i + 1}{chemin.suffix}") for i in range(n)]


def exporter_plaques(cfg: Plaques, chemin, p: ParametresImpression | None = None,
                     par_plaque: bool = False) -> list[tuple[Path, Trajet]]:
    """Écrit le(s) G-code(s) : un par lot (plateau plein) ou un par plaque."""
    p = p or ParametresImpression(**PETG_ARIANEPLAST)
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    lots, alertes = disposer(cfg, p)
    if par_plaque:              # une plaque seule, centrée sur le plateau
        champs = champs_effectifs(cfg)                 # ceux de la série entière
        lots = [disposer(replace(cfg, reglages=[r], champs=champs), p, [i + 1])[0][0]
                for i, r in enumerate(cfg.reglages)]
        alertes = [a for a in alertes if "dégagement" not in a and "lots" not in a]
        chemins = [chemin.with_name(f"{chemin.stem}_plaque{q[0].numero}{chemin.suffix}") for q in lots]
    else:
        chemins = _chemins(chemin, len(lots), "lot")
    res = []
    for c, lot in zip(chemins, lots):
        texte, trajet = generer_gcode_plaques(lot, cfg, p, nom=c.stem)
        trajet.avertissements[:0] = alertes
        c.write_text(texte, encoding="utf-8")
        res.append((c, trajet))
    return res


def exporter_stl_plaques(cfg: Plaques, chemin, p: ParametresImpression | None = None) -> list[Path]:
    """STL binaire(s) des plaques avec leur empreinte, disposées comme sur le plateau.

    Pour un trancheur : les réglages de chaque plaque restent à saisir à la main.
    """
    p = p or ParametresImpression(**PETG_ARIANEPLAST)
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    lots, _ = disposer(cfg, p)
    sorties = []
    for c, lot in zip(_chemins(chemin, len(lots), "lot"), lots):
        tris = np.concatenate([v[f] for v, f in (q.maillage() for q in lot)]).astype(np.float32)
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        with open(c, "wb") as fh:
            fh.write(b"generateur-formes plaques".ljust(80, b" "))
            fh.write(struct.pack("<I", len(tris)))
            data = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
            data["n"], data["v"] = n, tris
            fh.write(data.tobytes())
        sorties.append(c)
    return sorties


def exporter_fiche(cfg: Plaques, chemin, p: ParametresImpression | None = None) -> Path:
    """Fiche d'évaluation (CSV « ; », s'ouvre dans Excel / LibreOffice) à remplir après impression."""
    p = p or ParametresImpression(**PETG_ARIANEPLAST)
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    lots, _ = disposer(cfg, p)
    ordre = {q.numero: (i + 1, j + 1) for i, lot in enumerate(lots) for j, q in enumerate(lot)}
    with open(chemin, "w", newline="", encoding="utf-8-sig") as fh:
        ecr = csv.writer(fh, delimiter=";")
        ecr.writerow(["plaque", "lot", "ordre", "etiquette", "buse (°C)", "plateau (°C)", "debit",
                      "vitesse (mm/s)", "ventilateur (%)", "couche (mm)", "ligne (mm)", "lignes",
                      "transparence (0-5)", "bulles (0-5)", "lignes visibles (0-5)", "fils / cheveux (0-5)",
                      "adherence (0-5)", "remarques"])
        for i, r in enumerate(cfg.reglages):
            lot, rang = ordre[i + 1]
            ecr.writerow([i + 1, lot, rang, " ".join(r.etiquette(i + 1, champs_effectifs(cfg))), r.temp_buse,
                          p.temp_plateau, f"{r.flux:.2f}".replace(".", ","), f"{r.vitesse:g}".replace(".", ","),
                          r.ventilateur, f"{r.hauteur_couche:.2f}".replace(".", ","),
                          f"{r.largeur_ligne:.2f}".replace(".", ","), r.motif] + [""] * 6)
        ecr.writerow([])
        for lettre, sens in LEGENDE.items():
            ecr.writerow([lettre, sens])
    return chemin


def figure_plaques(cfg: Plaques, p: ParametresImpression | None = None, lot: int = 0,
                   titre: str = "Plaques de test"):
    """Vue 3D d'un lot : plaques translucides, empreinte visible, réglages au survol."""
    from .visualisation import _go, _scene

    go = _go()
    p = p or ParametresImpression(**PETG_ARIANEPLAST)
    lots, _ = disposer(cfg, p)
    fig = go.Figure()
    for q in lots[min(lot, len(lots) - 1)]:
        v, f = q.maillage()
        r = q.reglage
        survol = (f"plaque {q.numero}<br>buse {r.temp_buse} °C · débit {r.flux:.2f}<br>"
                  f"vitesse {r.vitesse:g} mm/s · ventilateur {r.ventilateur} %<br>"
                  f"couche {r.hauteur_couche:.2f} mm · ligne {r.largeur_ligne:.2f} mm · {r.motif}")
        fig.add_trace(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2],
                                color="#9fd8e6", opacity=0.55, flatshading=True, name=f"plaque {q.numero}",
                                hovertext=survol, hoverinfo="text", showlegend=False))
        c = q.origine + [q.largeur / 2, q.longueur - 6]
        fig.add_trace(go.Scatter3d(x=[c[0]], y=[c[1]], z=[q.epaisseur + 1], mode="text",
                                   text=[f"#{q.numero}"], textfont=dict(color="white", size=14),
                                   showlegend=False, hoverinfo="skip"))
    fig = _scene(fig, titre)
    # plaques très plates : rapport d'aspect imposé (sinon la vue « data » cadre trop près)
    mn = np.min([q.origine for q in lots[min(lot, len(lots) - 1)]], 0)
    mx = np.max([q.origine + [q.largeur, q.longueur] for q in lots[min(lot, len(lots) - 1)]], 0)
    dx, dy = mx - mn
    m = max(dx, dy)
    fig.update_layout(scene=dict(aspectmode="manual",
                                 aspectratio=dict(x=dx / m, y=dy / m, z=0.12),
                                 zaxis=dict(range=[0, max(6.0, cfg.epaisseur * 2)]),
                                 camera=dict(eye=dict(x=0.0, y=-1.25, z=1.15))))
    return fig


def resume(cfg: Plaques, p: ParametresImpression | None = None) -> dict:
    """Informations pour l'interface : nombre de lots, alertes, étiquettes."""
    p = p or ParametresImpression(**PETG_ARIANEPLAST)
    lots, av = disposer(cfg, p)
    return {"plaques": len(cfg.reglages), "lots": len(lots), "par_lot": len(lots[0]), "alertes": av,
            "etiquettes": [" / ".join(q.lignes_texte) for lot in lots for q in lot]}


__all__ = [
    "PETG_ARIANEPLAST", "REGLAGE_TRANSPARENT", "SERIES", "MOTIFS", "LEGENDE",
    "ReglagePlaque", "Plaques", "Plaque", "plan", "serie", "disposer",
    "generer_gcode_plaques", "exporter_plaques", "exporter_stl_plaques", "exporter_fiche",
    "figure_plaques", "resume", "ParametresImpression",
]
