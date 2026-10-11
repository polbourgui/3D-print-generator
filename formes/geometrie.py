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

def param(defaut, mini=None, maxi=None, pas=None, aide=""):
    """Déclare un paramètre de module avec ses bornes pour les curseurs."""
    return field(default=defaut, metadata={"min": mini, "max": maxi, "pas": pas, "aide": aide})


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

    def copie(self, **kw) -> "Forme":
        d = dict(pts=self.pts.copy(), nom=self.nom, fond=self.fond, ferme_haut=self.ferme_haut)
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
        if self.fond:
            sommets.append(np.r_[self.pts[0, :, :2].mean(0), self.z[0]][None])
            ring = idx[0]
            tris.append(np.stack([np.full(N, n), ring[np.r_[1:N, 0]], ring], -1))
            n += 1
        if self.ferme_haut:
            sommets.append(np.r_[self.pts[-1, :, :2].mean(0), self.z[-1]][None])
            ring = idx[-1]
            tris.append(np.stack([np.full(N, n), ring, ring[np.r_[1:N, 0]]], -1))
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
        """
        posees, flottantes = [], []
        for p in self.pieces:
            (flottantes if p.boite()[0][2] > 1e-6 else posees).append(p)
        if not flottantes:
            return Assemblage(list(posees))
        res = list(posees)
        x_libre = max(p.boite()[1][0] for p in posees) + marge if posees else None
        cx = np.mean([p.centres().mean(0) for p in self.pieces], axis=0)
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
    def exporter_stl(self, chemin) -> Path:
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        tris = []
        for p in self.pieces:
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
