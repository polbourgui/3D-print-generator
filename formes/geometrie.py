"""Structures géométriques de base.

Une forme est décrite comme une pile de contours fermés horizontaux :
un tableau ``pts`` de dimension (L, N, 3) — L couches de N points chacune.
Toutes les couches ont le même nombre de points, ce qui permet d'interpoler
facilement entre deux couches (utile pour le G-code) et de construire un
maillage triangulé régulier.

Convention : dans une couche, la coordonnée z est constante, et les contours
sont parcourus dans le sens trigonométrique (CCW) vus de dessus.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np


# --------------------------------------------------------------------------
# Paramètres de modules (avec bornes, pour générer une interface automatique)
# --------------------------------------------------------------------------

def param(defaut, mini=None, maxi=None, pas=None, aide="", choix=None):
    """Déclare un paramètre de module avec ses bornes pour les curseurs.

    ``choix`` : liste de valeurs possibles (affichée en menu déroulant).
    """
    return field(default=defaut, metadata={"min": mini, "max": maxi, "pas": pas, "aide": aide,
                                            "choix": choix})


@dataclass
class Module:
    """Classe de base des modules activables (déformations et emboîtements)."""

    actif: bool = field(default=True, kw_only=True)

    @property
    def nom(self) -> str:
        return type(self).__name__

    def parametres(self):
        """Liste des (nom, valeur, métadonnées) des paramètres réglables."""
        return [(f.name, getattr(self, f.name), f.metadata)
                for f in fields(self) if f.name != "actif"]

    def __repr__(self):
        etat = "on " if self.actif else "off"
        args = ", ".join(f"{n}={v:g}" if isinstance(v, float) else f"{n}={v}"
                         for n, v, _ in self.parametres())
        return f"[{etat}] {self.nom}({args})"


# --------------------------------------------------------------------------
# Formes
# --------------------------------------------------------------------------

@dataclass
class Forme:
    pts: np.ndarray            # (L, N, 3)
    nom: str = "forme"
    fond: bool = True          # la pièce a-t-elle un fond plein (G-code) ?
    ferme_haut: bool = False   # fermer le haut du maillage (visualisation/STL)
    retournee: bool = False    # montrée à l'envers : à retourner pour l'impression
    # fond / dessus percés pour une douille : (diamètre du perçage, hauteur du manchon) en mm,
    # centrés sur la couche du bas / du haut ; le manchon part du fond vers l'intérieur
    douille_bas: tuple | None = None
    douille_haut: tuple | None = None
    dentelle: object | None = None   # module Dentelle : paroi en filet non planaire (G-code)

    def copie(self, **kw) -> "Forme":
        d = dict(pts=self.pts.copy(), nom=self.nom, fond=self.fond, ferme_haut=self.ferme_haut,
                 retournee=self.retournee, douille_bas=self.douille_bas, douille_haut=self.douille_haut,
                 dentelle=self.dentelle)
        d.update(kw)
        return Forme(**d)

    # -- informations ------------------------------------------------------
    @property
    def z(self) -> np.ndarray:
        return self.pts[:, 0, 2]

    @property
    def hauteur(self) -> float:
        return float(self.z[-1] - self.z[0])

    def t(self) -> np.ndarray:
        """Hauteur normalisée de chaque couche dans [0, 1] (forme (L, 1))."""
        z = self.z
        h = max(z[-1] - z[0], 1e-9)
        return ((z - z[0]) / h)[:, None]

    def centres(self) -> np.ndarray:
        """Centre (x, y) de chaque couche, forme (L, 2)."""
        return self.pts[:, :, :2].mean(axis=1)

    def boite(self):
        p = self.pts.reshape(-1, 3)
        return p.min(axis=0), p.max(axis=0)

    # -- transformations -----------------------------------------------------
    def translater(self, dx=0.0, dy=0.0, dz=0.0) -> "Forme":
        f = self.copie()
        f.pts += np.array([dx, dy, dz])
        return f

    def retourner(self) -> "Forme":
        """Demi-tour autour d'un axe horizontal (x) passant par le centre de la pièce.

        L'ordre des couches est inversé pour que z reste croissant, et celui des
        points pour que les contours restent dans le sens trigonométrique.
        """
        mn, mx = self.boite()
        pts = self.pts[::-1, ::-1].copy()
        pts[:, :, 1] = mn[1] + mx[1] - pts[:, :, 1]
        pts[:, :, 2] = mn[2] + mx[2] - pts[:, :, 2]
        return self.copie(pts=pts, fond=self.ferme_haut, ferme_haut=self.fond,
                          douille_bas=self.douille_haut, douille_haut=self.douille_bas,
                          retournee=not self.retournee)

    def contour_a(self, z: float) -> np.ndarray:
        """Contour (N, 2) interpolé linéairement à la hauteur z."""
        zs = self.z
        if z <= zs[0]:
            return self.pts[0, :, :2]
        if z >= zs[-1]:
            return self.pts[-1, :, :2]
        i = int(np.searchsorted(zs, z) - 1)
        i = min(max(i, 0), len(zs) - 2)
        a = (z - zs[i]) / max(zs[i + 1] - zs[i], 1e-12)
        return (1 - a) * self.pts[i, :, :2] + a * self.pts[i + 1, :, :2]

    # -- maillage -------------------------------------------------------------
    def maillage(self):
        """Renvoie (sommets (V,3), triangles (F,3)) de la surface."""
        L, N, _ = self.pts.shape
        sommets = [self.pts.reshape(-1, 3)]
        idx = np.arange(L * N).reshape(L, N)
        a = idx[:-1, :]
        b = idx[:-1, np.r_[1:N, 0]]
        c = idx[1:, np.r_[1:N, 0]]
        d = idx[1:, :]
        tris = [np.stack([a, b, c], -1).reshape(-1, 3),
                np.stack([a, c, d], -1).reshape(-1, 3)]
        n = L * N
        suiv = np.r_[1:N, 0]
        for actif, couche, douille, sens in [(self.fond, 0, self.douille_bas, 1),
                                             (self.ferme_haut, -1, self.douille_haut, -1)]:
            if not actif:
                continue
            ring = idx[couche]
            z0 = self.z[couche]
            c = self.pts[couche, :, :2].mean(0)
            if douille is None:                      # disque plein
                sommets.append(np.r_[c, z0][None])
                a, b = (ring[suiv], ring) if sens > 0 else (ring, ring[suiv])
                tris.append(np.stack([np.full(N, n), a, b], -1))
                n += 1
                continue
            # couronne entre le contour et le perçage, puis manchon éventuel
            d = self.pts[couche, :, :2] - c
            ang = np.arctan2(d[:, 1], d[:, 0])
            cercle = c + douille[0] / 2 * np.column_stack([np.cos(ang), np.sin(ang)])
            sommets.append(np.column_stack([cercle, np.full(N, z0)]))
            trou = np.arange(n, n + N)
            n += N
            q = [trou, ring[suiv], ring, trou[suiv]]
            if sens < 0:
                q = [trou, ring, ring[suiv], trou[suiv]]
            tris += [np.stack([q[0], q[1], q[2]], -1), np.stack([q[0], q[3], q[1]], -1)]
            if douille[1] > 0:
                sommets.append(np.column_stack([cercle, np.full(N, z0 + sens * douille[1])]))
                bout = np.arange(n, n + N)
                n += N
                tris += [np.stack([trou, bout, bout[suiv]], -1), np.stack([trou, bout[suiv], trou[suiv]], -1)]
        return np.concatenate(sommets), np.concatenate(tris).astype(np.int64)


@dataclass
class Assemblage:
    """Ensemble de pièces (résultat d'un emboîtement)."""

    pieces: list[Forme] = field(default_factory=list)

    def __iter__(self):
        return iter(self.pieces)

    def __len__(self):
        return len(self.pieces)

    def boite(self):
        b = [p.boite() for p in self.pieces]
        return np.min([x[0] for x in b], 0), np.max([x[1] for x in b], 0)

    def pour_impression(self, marge: float = 5.0) -> "Assemblage":
        """Pose chaque pièce flottante sur le plateau et l'écarte des autres.

        Les pièces qui touchent déjà le plateau (z = 0) restent en place :
        c'est ce qui permet d'imprimer des pièces gigognes « en place ».
        Les pièces montrées à l'envers (``retournee``, ex. un couvercle) sont
        d'abord remises dans leur sens d'impression.
        """
        pieces = [p.retourner() if p.retournee else p for p in self.pieces]
        posees, flottantes = [], []
        for p in pieces:
            (flottantes if p.boite()[0][2] > 1e-6 else posees).append(p)
        if not flottantes:
            return Assemblage(list(posees))
        res = list(posees)
        x_libre = max(p.boite()[1][0] for p in posees) + marge if posees else None
        cx = np.mean([p.centres().mean(0) for p in pieces], axis=0)
        for p in flottantes:
            q = p.translater(dz=-p.boite()[0][2])
            if x_libre is not None:
                q = q.translater(dx=x_libre - q.boite()[0][0])
            x_libre = q.boite()[1][0] + marge
            res.append(q)
        # recentrer l'ensemble sur le centre initial
        mn, mx = Assemblage(res).boite()
        dx, dy = cx - (mn[:2] + mx[:2]) / 2
        return Assemblage([r.translater(dx, dy) for r in res])

    # -- export STL -------------------------------------------------------------
    def exporter_stl(self, chemin, impression: bool = True) -> Path:
        """Exporte en STL binaire.

        ``impression=True`` : pièces posées sur le plateau, côte à côte et dans
        leur sens d'impression (prêt pour un trancheur). ``False`` : disposition
        de la vue 3D (vue éclatée, couvercle en place…).
        """
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        tris = []
        for p in (self.pour_impression() if impression else self).pieces:
            v, f = p.maillage()
            tris.append(v[f])
        tris = np.concatenate(tris).astype(np.float32)
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        with open(chemin, "wb") as fh:
            fh.write(b"generateur-formes".ljust(80, b" "))
            fh.write(struct.pack("<I", len(tris)))
            data = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
            data["n"], data["v"] = n, tris
            fh.write(data.tobytes())
        return chemin


# --------------------------------------------------------------------------
# Outils 2D
# --------------------------------------------------------------------------

def normales_2d(contour: np.ndarray) -> np.ndarray:
    """Normales sortantes unitaires d'un contour fermé CCW (N, 2)."""
    tan = np.roll(contour, -1, axis=0) - np.roll(contour, 1, axis=0)
    n = np.stack([tan[:, 1], -tan[:, 0]], axis=-1)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def decaler_contour(contour: np.ndarray, d: float) -> np.ndarray:
    """Décale un contour le long de ses normales (d < 0 : vers l'intérieur).

    Approximation par les normales : valable tant que |d| reste inférieur au
    rayon de courbure local (sinon le contour se recoupe).
    """
    return contour + d * normales_2d(contour)


def aire_signee(contour: np.ndarray) -> float:
    x, y = contour[:, 0], contour[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def enveloppe_convexe(points: np.ndarray) -> np.ndarray:
    """Enveloppe convexe 2D (algorithme de la chaîne monotone), sens CCW."""
    p = np.unique(np.round(np.asarray(points)[:, :2], 6), axis=0)
    if len(p) < 3:
        return p

    def croix(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    bas, haut = [], []
    for q in p:
        while len(bas) >= 2 and croix(bas[-2], bas[-1], q) <= 0:
            bas.pop()
        bas.append(q)
    for q in p[::-1]:
        while len(haut) >= 2 and croix(haut[-2], haut[-1], q) <= 0:
            haut.pop()
        haut.append(q)
    return np.array(bas[:-1] + haut[:-1])
