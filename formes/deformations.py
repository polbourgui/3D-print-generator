"""Modules de déformation.

Chaque module prend une ``Forme`` et renvoie une nouvelle ``Forme``.
Règle commune : les déformations ne modifient que x et y (jamais z), afin que
chaque couche reste horizontale — condition nécessaire pour le G-code.

Les déformations s'appliquent dans l'ordre de la liste : l'ordre compte
(une torsion appliquée avant ou après une ondulation ne donne pas le même résultat).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometrie import Forme, Module, normales_2d, param


class Deformation(Module):
    def appliquer(self, forme: Forme) -> Forme:  # pragma: no cover - interface
        raise NotImplementedError


def _polaire(forme: Forme):
    """(rayon, angle) de chaque point autour du centre de sa couche."""
    c = forme.centres()[:, None, :]
    d = forme.pts[:, :, :2] - c
    return c, np.hypot(d[..., 0], d[..., 1]), np.arctan2(d[..., 1], d[..., 0])


def _angle_param(forme: Forme) -> np.ndarray:
    """Angle « paramétrique » de chaque point : son indice sur le contour.

    Contrairement à l'angle géométrique, il ne dépend pas des déformations
    précédentes et garantit une forme sans couture (périodique).
    """
    L, N, _ = forme.pts.shape
    return np.broadcast_to(np.linspace(0, 2 * np.pi, N, endpoint=False), (L, N))


def _deplacer_radial(forme: Forme, dr: np.ndarray) -> Forme:
    """Déplace chaque point le long de la normale de son contour."""
    f = forme.copie()
    for i in range(f.pts.shape[0]):
        f.pts[i, :, :2] += dr[i][:, None] * normales_2d(f.pts[i, :, :2])
    return f


def _mise_a_echelle(forme: Forme, s: np.ndarray) -> Forme:
    """Mise à l'échelle XY couche par couche autour du centre de chaque couche."""
    f = forme.copie()
    c = f.centres()[:, None, :]
    f.pts[:, :, :2] = c + (f.pts[:, :, :2] - c) * s.reshape(-1, 1, 1)
    return f


@dataclass
class Torsion(Deformation):
    """Rotation progressive des couches autour de l'axe vertical."""

    angle: float = param(90.0, -720, 720, 5, "rotation totale bas→haut (degrés)")
    acceleration: float = param(1.0, 0.2, 4.0, 0.1, "1 = linéaire, >1 = torsion concentrée en haut")

    def appliquer(self, forme):
        f = forme.copie()
        a = np.radians(self.angle) * forme.t()[:, 0] ** self.acceleration
        c = f.centres()[:, None, :]
        d = f.pts[:, :, :2] - c
        cos, sin = np.cos(a)[:, None], np.sin(a)[:, None]
        f.pts[:, :, 0] = c[..., 0] + d[..., 0] * cos - d[..., 1] * sin
        f.pts[:, :, 1] = c[..., 1] + d[..., 0] * sin + d[..., 1] * cos
        return f


@dataclass
class Fuseau(Deformation):
    """Profil vertical : évasement/rétrécissement et ventre (galbe)."""

    echelle_bas: float = param(1.0, 0.2, 2.0, 0.05, "échelle au pied")
    echelle_haut: float = param(0.7, 0.2, 2.0, 0.05, "échelle au sommet")
    ventre: float = param(0.25, -0.6, 1.0, 0.05, "galbe (+ ventru / − cintré)")
    position_ventre: float = param(0.4, 0.05, 0.95, 0.05, "hauteur relative du ventre")

    def appliquer(self, forme):
        t = forme.t()[:, 0]
        p = np.clip(self.position_ventre, 0.01, 0.99)
        # bosse qui vaut 0 en bas et en haut, 1 à la position p
        u = np.where(t < p, t / p, (1 - t) / (1 - p))
        bosse = np.sin(np.pi / 2 * u) ** 2
        s = self.echelle_bas + (self.echelle_haut - self.echelle_bas) * t + self.ventre * bosse
        return _mise_a_echelle(forme, np.maximum(s, 0.05))


@dataclass
class Ondulation(Deformation):
    """Vagues radiales qui tournent en montant (motif hélicoïdal)."""

    amplitude: float = param(3.0, 0, 20, 0.5, "amplitude (mm)")
    lobes: int = param(8, 1, 64, 1, "nombre d'ondes sur le tour")
    tours: float = param(1.0, -10, 10, 0.25, "décalage de phase bas→haut (en ondes)")
    vagues_verticales: float = param(0.0, 0, 20, 0.5, "ondes le long de la hauteur")

    def appliquer(self, forme):
        th = _angle_param(forme)
        t = forme.t()
        phase = 2 * np.pi * self.tours * t
        dr = self.amplitude * np.sin(int(self.lobes) * th + phase)
        if self.vagues_verticales:
            dr = dr * (0.5 + 0.5 * np.cos(2 * np.pi * self.vagues_verticales * t))
        return _deplacer_radial(forme, dr)


@dataclass
class Plis(Deformation):
    """Plissé façon papier : profil en dents de scie (arêtes vives)."""

    profondeur: float = param(4.0, 0, 20, 0.5, "profondeur des plis (mm)")
    nombre: int = param(24, 3, 96, 1, "nombre de plis")
    attenuation: float = param(0.0, 0, 1, 0.05, "atténuation vers le haut (0 = aucune)")

    def appliquer(self, forme):
        th = _angle_param(forme)
        triangle = 2 * np.abs(((int(self.nombre) * th / (2 * np.pi)) % 1) - 0.5)  # 0..1
        dr = self.profondeur * (triangle - 0.5)
        dr = dr * (1 - self.attenuation * forme.t())
        return _deplacer_radial(forme, dr)


@dataclass
class Bruit(Deformation):
    """Bruit organique lisse (somme de sinusoïdes aléatoires, sans couture)."""

    amplitude: float = param(4.0, 0, 20, 0.5, "amplitude (mm)")
    detail: int = param(6, 1, 24, 1, "fréquence angulaire maximale")
    frequence_verticale: float = param(2.0, 0, 12, 0.25, "variations sur la hauteur")
    octaves: int = param(5, 1, 16, 1, "nombre de composantes")
    graine: int = param(7, 0, 9999, 1, "graine aléatoire")

    def appliquer(self, forme):
        rng = np.random.default_rng(int(self.graine))
        th, t = _angle_param(forme), forme.t()
        dr = np.zeros_like(th)
        for _ in range(int(self.octaves)):
            k = rng.integers(1, int(self.detail) + 1)          # entier → périodique
            fz = rng.uniform(0, self.frequence_verticale)
            ph1, ph2 = rng.uniform(0, 2 * np.pi, 2)
            dr += np.sin(k * th + ph1) * np.cos(2 * np.pi * fz * t + ph2) / np.sqrt(k)
        dr *= self.amplitude / max(np.abs(dr).max(), 1e-9)
        return _deplacer_radial(forme, dr)


@dataclass
class Courbure(Deformation):
    """Inclinaison / courbure de l'axe (la forme « penche »).

    Attention aux porte-à-faux : au-delà d'environ 45° la pièce n'est plus
    imprimable sans support. Le G-code affiche un avertissement.
    """

    fleche: float = param(15.0, -80, 80, 1, "déport du sommet (mm)")
    direction: float = param(0.0, 0, 360, 5, "direction du déport (degrés)")
    exposant: float = param(2.0, 1.0, 4.0, 0.1, "1 = inclinaison droite, 2 = arc")
    oscillations: float = param(0.0, 0, 6, 0.25, "serpentin : nombre d'aller-retours")

    def appliquer(self, forme):
        f = forme.copie()
        t = forme.t()[:, 0]
        if self.oscillations:
            dep = self.fleche * np.sin(2 * np.pi * self.oscillations * t) * t ** (self.exposant - 1)
        else:
            dep = self.fleche * t ** self.exposant
        a = np.radians(self.direction)
        f.pts[:, :, 0] += (dep * np.cos(a))[:, None]
        f.pts[:, :, 1] += (dep * np.sin(a))[:, None]
        return f


@dataclass
class Pincement(Deformation):
    """Pincement elliptique : la section s'aplatit et tourne avec la hauteur."""

    intensite: float = param(0.3, 0, 0.9, 0.05, "aplatissement (0 = aucun)")
    rotation: float = param(90.0, -360, 360, 5, "rotation de l'axe de pincement (degrés)")
    pulsations: float = param(1.0, 0, 8, 0.25, "nombre de pincements sur la hauteur")

    def appliquer(self, forme):
        f = forme.copie()
        t = forme.t()[:, 0]
        k = self.intensite * np.abs(np.sin(np.pi * self.pulsations * t)) if self.pulsations \
            else np.full_like(t, self.intensite)
        a = np.radians(self.rotation) * t
        c = f.centres()[:, None, :]
        d = f.pts[:, :, :2] - c
        ca, sa = np.cos(a)[:, None], np.sin(a)[:, None]
        u = d[..., 0] * ca + d[..., 1] * sa          # axe long
        v = -d[..., 0] * sa + d[..., 1] * ca         # axe court
        u = u * (1 + k[:, None] / 2)
        v = v * (1 - k[:, None] / 2)
        f.pts[:, :, 0] = c[..., 0] + u * ca - v * sa
        f.pts[:, :, 1] = c[..., 1] + u * sa + v * ca
        return f


TOUTES = [Torsion, Fuseau, Ondulation, Plis, Bruit, Courbure, Pincement]
