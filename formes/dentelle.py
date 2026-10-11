"""Dentelle verticale en impression non planaire.

La paroi n'est plus une pile de tours plats : la buse suit une vague en Z.
Chaque tour reprend la vague du précédent décalée d'une demi-période ; les
creux d'un tour se posent sur les crêtes du précédent (nœuds soudés) et,
entre deux nœuds, le brin passe dans le vide : la paroi devient un filet.

Trajet (u = nombre de tours depuis le début, θ = angle sur le tour) ::

    z(u) = base(u) + 2·a(u)·f(n·θ + π·u)
    base(u) = base(u − 1) + h + 2·a(u − 1)

``f`` vaut 0 au creux, 1 à la crête, et vérifie f(x + π) = 1 − f(x). Alors

    z(u) − z(u − 1) = h + 2·a(u−1)·(1 − f(u−1)) + 2·a(u)·f(u)  ≥  h

avec égalité aux nœuds : la buse ne descend jamais dans la matière déjà posée,
et chaque brin s'appuie exactement d'une hauteur de couche sur le précédent.
Avec a = 0 on retrouve le mode vase classique (bords pleins), et ``a`` peut
varier lentement (montée en douceur, maille progressive) sans casser la règle.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometrie import Forme, Module, param

MOTIFS = ("losanges", "zigzag", "alveoles")


def motif(nom: str, x: np.ndarray) -> np.ndarray:
    """Vague de période 2π, 0 en x = 0, 1 en x = π, avec f(x + π) = 1 − f(x)."""
    fr = (x / (2 * np.pi)) % 1
    if nom == "losanges":                       # sinus : mailles arrondies
        return (1 - np.cos(x)) / 2
    zig = 1 - np.abs(1 - 2 * fr)                # triangle : losanges à angles vifs
    if nom == "zigzag":
        return zig
    if nom == "alveoles":                       # trapèze : nœuds allongés → alvéoles
        return np.clip((zig - 0.5) * 2 + 0.5, 0, 1)
    raise ValueError(f"motif inconnu : {nom!r} (choix : {', '.join(MOTIFS)})")


def _point_surface(forme: Forme, indice: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Point (x, y) de la surface à l'indice de contour (réel) et à la hauteur z."""
    L, N, _ = forme.pts.shape
    li = np.interp(z, forme.z, np.arange(L))
    l0 = np.minimum(np.floor(li).astype(int), L - 2)
    al = (li - l0)[:, None]
    i0 = np.floor(indice).astype(int) % N
    i1 = (i0 + 1) % N
    ai = (indice - np.floor(indice))[:, None]
    p = forme.pts[:, :, :2]
    bas = (1 - ai) * p[l0, i0] + ai * p[l0, i1]
    haut = (1 - ai) * p[l0 + 1, i0] + ai * p[l0 + 1, i1]
    return (1 - al) * bas + al * haut


@dataclass
class Dentelle(Module):
    """Paroi ajourée en filet, imprimée en un seul brin non planaire (G-code).

    Une maille (un losange) fait ``hauteur_maille`` de haut et
    périmètre / ``cellules`` de large. La maille peut grandir ou rétrécir
    progressivement jusqu'à ``maille_haut`` (0 = identique en haut).
    Les bords pleins (mode vase classique) rigidifient la pièce.

    Conseils : ventilation à fond (forcée), vitesse lente, mailles plutôt plus
    larges que hautes. La vitesse de l'axe Z est limitée par ``vitesse_z_max``
    (onglet Impression). Le STL et la vue pleine ne montrent pas les jours :
    seul le G-code (et la vue des brins) contient la dentelle.
    """

    motif: str = param("losanges", aide="forme des mailles", choix=MOTIFS)
    cellules: int = param(12, 3, 60, 1, "mailles sur le tour")
    hauteur_maille: float = param(8.0, 2, 30, 0.5, "hauteur d'une maille en bas (mm)")
    maille_haut: float = param(0.0, 0, 30, 0.5, "hauteur d'une maille en haut (mm, 0 = identique)")
    bord_bas: float = param(3.0, 0, 40, 0.5, "bord plein en bas, au-dessus du fond (mm)")
    bord_haut: float = param(3.0, 0, 40, 0.5, "bord plein en haut (mm)")
    vitesse: float = param(12.0, 3, 40, 1, "vitesse d'impression de la dentelle (mm/s)")

    def amplitude(self, hauteur_maille, h: float):
        """Demi-amplitude a de la vague pour une maille donnée (2 tours = 1 maille)."""
        return np.maximum((np.asarray(hauteur_maille, float) / 2 - h) / 2, 0.0)

    def trajet(self, forme: Forme, h: float, z_debut: float | None = None):
        """Trajet de buse (M, 3) depuis ``z_debut`` jusqu'au sommet, et nombre de tours.

        Le trajet commence au point 0 du contour, à ``z_debut`` (dessus du fond).
        """
        L, N, _ = forme.pts.shape
        z_bas, z_haut = float(forme.z[0]), float(forme.z[-1])
        z0 = z_bas if z_debut is None else float(z_debut)
        n = int(self.cellules)
        M = max(N, 24 * n)                        # points par tour
        m_haut = self.maille_haut or self.hauteur_maille
        debut_jours = z0 + self.bord_bas
        fin_jours = z_haut - self.bord_haut
        a_max = float(self.amplitude(max(self.hauteur_maille, m_haut), h))
        pas_rampe = max(a_max, 1e-9) / M          # l'amplitude change en un tour au plus
        idx = np.arange(M)
        theta = 2 * np.pi * idx / M

        tours_z, base_prec, a_prec = [], None, None
        a_courant = 0.0
        for j in range(100_000):
            u = j + idx / M
            if base_prec is None:
                base = z0 + h * idx / M
            else:
                base = base_prec + h + 2 * a_prec
            # amplitude visée : maille interpolée sur la hauteur, nulle dans les bords
            t = np.clip((base - debut_jours) / max(fin_jours - debut_jours, 1e-9), 0, 1)
            cible = self.amplitude(self.hauteur_maille + (m_haut - self.hauteur_maille) * t, h)
            # la crête du tour (base + 2a) et le tour de descente doivent rester sous fin_jours
            dans_jours = (base >= debut_jours) & (base + 4 * cible + 2 * h <= fin_jours + 2 * cible)
            cible = np.where(dans_jours, cible, 0.0)
            a = np.empty(M)
            for i in range(M):                    # montée / descente progressive
                a_courant = min(max(cible[i], a_courant - pas_rampe), a_courant + pas_rampe)
                a[i] = a_courant
            z = base + 2 * a * motif(self.motif, n * theta + np.pi * u)
            fini = base >= z_haut - 1e-9
            if fini.any() or z.max() > z_haut:
                # dernier tour : écrêté au sommet, et arrêté avant de passer à moins
                # de h au-dessus du tour précédent (la buse écraserait le brin)
                z = np.minimum(z, z_haut)
                k = int(np.argmax(fini)) if fini.any() else M - 1
                if base_prec is not None:
                    trop_bas = z[:k + 1] < tours_z[-1][1][:k + 1] + h - 1e-9 if len(tours_z[-1][1]) == M \
                        else np.zeros(k + 1, bool)
                    if trop_bas.any():
                        k = int(np.argmax(trop_bas)) - 1
                if k >= 0:
                    tours_z.append((idx[:k + 1], z[:k + 1]))
                break
            tours_z.append((idx, z))
            base_prec, a_prec = base, a
        indices = np.concatenate([i / M * N for i, _ in tours_z])
        zs = np.concatenate([z for _, z in tours_z])
        xy = _point_surface(forme, indices, zs)
        return np.column_stack([xy, zs]), len(tours_z), M

    def resume(self, forme: Forme, h: float) -> dict:
        """Dimensions utiles d'une maille (pour l'interface et les avertissements)."""
        c = forme.pts[len(forme.pts) // 2, :, :2]
        perimetre = float(np.linalg.norm(np.diff(c, axis=0, append=c[:1]), axis=1).sum())
        largeur = perimetre / int(self.cellules)
        a = float(self.amplitude(max(self.hauteur_maille, self.maille_haut or 0), h))
        # pente maximale d'un brin (vague sinusoïdale z = a(1 − cos kx), k = 2π / largeur)
        pente = np.degrees(np.arctan(2 * np.pi * a / largeur))
        return {"largeur": largeur, "hauteur": self.hauteur_maille, "pente": float(pente), "a": a}
