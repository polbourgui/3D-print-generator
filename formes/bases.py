"""Formes de base : un profil 2D (section) extrudé sur une hauteur."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometrie import Forme, Module, param

PROFILS = ("cercle", "polygone", "etoile", "superellipse", "goutte", "fleur", "engrenage")


@dataclass
class Base(Module):
    """Section extrudée verticalement.

    profil :
      - ``cercle``
      - ``polygone``     : ``cotes`` côtés, angles légèrement arrondis par ``arrondi``
      - ``etoile``       : ``cotes`` branches, creux réglé par ``creux``
      - ``superellipse`` : carré arrondi (exposant ``exposant``, 2 = cercle)
      - ``goutte``       : forme asymétrique
      - ``fleur``        : ``cotes`` pétales arrondis, échancrure réglée par ``creux``
      - ``engrenage``    : ``cotes`` dents trapézoïdales, profondeur réglée par ``creux``
    """

    profil: str = "cercle"
    rayon: float = param(40.0, 5, 120, 1, "rayon de la section (mm)")
    hauteur: float = param(100.0, 5, 250, 1, "hauteur totale (mm)")
    couches: int = param(120, 10, 600, 10, "résolution verticale (couches de calcul)")
    points: int = param(240, 24, 1440, 24, "points par contour")
    cotes: int = param(6, 3, 24, 1, "côtés / branches")
    creux: float = param(0.35, 0.0, 0.9, 0.01, "profondeur des creux (étoile, fleur, engrenage)")
    arrondi: float = param(0.15, 0.0, 1.0, 0.01, "arrondi des angles (polygone)")
    exposant: float = param(4.0, 1.0, 12.0, 0.1, "exposant (superellipse)")

    def rayon_polaire(self, theta: np.ndarray) -> np.ndarray:
        """Rayon de la section en fonction de l'angle (profil étoilé)."""
        r0, n = self.rayon, max(int(self.cotes), 3)
        if self.profil == "cercle":
            return np.full_like(theta, r0)
        if self.profil == "polygone":
            # rayon d'un polygone régulier, adouci par mélange avec un cercle
            secteur = 2 * np.pi / n
            a = (theta % secteur) - secteur / 2
            r_poly = r0 * np.cos(np.pi / n) / np.cos(a)
            return (1 - self.arrondi) * r_poly + self.arrondi * r0
        if self.profil == "etoile":
            return r0 * (1 - self.creux * (0.5 - 0.5 * np.cos(n * theta)))
        if self.profil == "superellipse":
            p = max(self.exposant, 1e-3)
            return r0 * (np.abs(np.cos(theta)) ** p + np.abs(np.sin(theta)) ** p) ** (-1 / p)
        if self.profil == "goutte":
            return r0 * (0.75 + 0.25 * np.cos(theta)) * (1 + 0.15 * np.cos(2 * theta))
        if self.profil == "fleur":
            return r0 * (1 - self.creux * np.abs(np.sin(n * theta / 2)))
        if self.profil == "engrenage":
            tri = 1 - 2 * np.abs((n * theta / (2 * np.pi)) % 1 - 0.5)    # 0 au creux, 1 en haut de dent
            dent = np.clip(2.5 * tri - 0.75, 0, 1)                         # flancs droits, sommet plat
            return r0 * (1 - self.creux * (1 - dent))
        raise ValueError(f"profil inconnu : {self.profil!r} (choix : {', '.join(PROFILS)})")

    def construire(self) -> Forme:
        L, N = int(self.couches) + 1, int(self.points)
        theta = np.linspace(0, 2 * np.pi, N, endpoint=False)
        r = self.rayon_polaire(theta)
        z = np.linspace(0, self.hauteur, L)
        pts = np.empty((L, N, 3))
        pts[:, :, 0] = r * np.cos(theta)
        pts[:, :, 1] = r * np.sin(theta)
        pts[:, :, 2] = z[:, None]
        return Forme(pts, nom=f"base-{self.profil}")
