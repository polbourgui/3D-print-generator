"""Modules d'emboîtement : transforment une forme en un assemblage de pièces.

- ``Gigogne``    : coques imbriquées les unes dans les autres (poupées russes),
                   imprimables « en place » en une seule fois (mode couches).
- ``Empilement`` : modules empilables ; chaque pièce porte un col qui s'emboîte
                   dans le pied de la suivante.
- ``Reseau``     : copies disposées en grille, avec variation de rotation/échelle.
- ``Couvercle``  : ajoute un couvercle à col qui s'emboîte dans l'ouverture.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometrie import Assemblage, Forme, Module, decaler_contour, param


class Emboitement(Module):
    def appliquer(self, forme: Forme) -> Assemblage:  # pragma: no cover - interface
        raise NotImplementedError


def _decaler_forme(forme: Forme, d: float) -> Forme:
    f = forme.copie()
    for i in range(f.pts.shape[0]):
        f.pts[i, :, :2] = decaler_contour(f.pts[i, :, :2], d)
    return f


def _couper_haut(forme: Forme, hauteur: float) -> Forme:
    """Garde les couches jusqu'à ``hauteur`` (la dernière est interpolée)."""
    z0 = forme.z[0]
    zmax = z0 + hauteur
    garde = forme.z < zmax - 1e-9
    pts = forme.pts[garde]
    dernier = np.concatenate([forme.contour_a(zmax), np.full((pts.shape[1], 1), zmax)], axis=1)
    return forme.copie(pts=np.concatenate([pts, dernier[None]], axis=0))


@dataclass
class Gigogne(Emboitement):
    """Coques concentriques : chaque coque est la précédente décalée vers l'intérieur.

    L'écart entre deux parois = ``paroi`` (épaisseur imprimée) + ``jeu``.
    Chaque coque intérieure est aussi un peu plus basse que la précédente.
    """

    nombre: int = param(3, 2, 8, 1, "nombre de coques")
    paroi: float = param(0.8, 0.4, 4, 0.1, "épaisseur de paroi imprimée (mm)")
    jeu: float = param(1.5, 0.3, 10, 0.1, "espace libre entre deux coques (mm)")
    retrait_hauteur: float = param(8.0, 0, 50, 1, "chaque coque est plus basse de (mm)")

    def appliquer(self, forme):
        pieces = []
        for k in range(int(self.nombre)):
            p = _decaler_forme(forme, -k * (self.paroi + self.jeu))
            h = forme.hauteur - k * self.retrait_hauteur
            if h <= 1:
                break
            p = _couper_haut(p, h)
            p.nom = f"coque-{k + 1}"
            pieces.append(p)
        return Assemblage(pieces)


@dataclass
class Empilement(Emboitement):
    """Modules empilables avec col d'emboîtement.

    La forme est découpée en ``nombre`` tronçons. Chaque tronçon (sauf le
    dernier) reçoit au sommet un col rétréci de ``paroi + jeu`` qui vient se
    loger dans le pied du tronçon suivant. Le rétrécissement se fait par un
    chanfrein à 45° pour rester imprimable sans support.
    Les tronçons supérieurs sont imprimés sans fond (ce sont des bagues).
    """

    nombre: int = param(3, 2, 8, 1, "nombre de modules")
    hauteur_col: float = param(8.0, 2, 30, 0.5, "hauteur du col (mm)")
    paroi: float = param(0.8, 0.4, 4, 0.1, "épaisseur de paroi imprimée (mm)")
    jeu: float = param(0.3, 0.05, 2, 0.05, "jeu d'emboîtement (mm)")
    ecart_vue: float = param(10.0, 0, 60, 1, "écart vertical dans la vue éclatée (mm)")

    def appliquer(self, forme):
        n = int(self.nombre)
        L = forme.pts.shape[0]
        bornes = np.linspace(0, L - 1, n + 1).round().astype(int)
        retrait = self.paroi + self.jeu
        dz = forme.hauteur / max(L - 1, 1)
        pieces = []
        for k in range(n):
            tr = forme.copie(pts=forme.pts[bornes[k]:bornes[k + 1] + 1].copy())
            tr.fond = k == 0
            if k < n - 1:
                tr = self._ajouter_col(tr, retrait, dz)
            tr.pts[:, :, 2] += k * self.ecart_vue
            tr.nom = f"module-{k + 1}"
            pieces.append(tr)
        return Assemblage(pieces)

    def _ajouter_col(self, tr: Forme, retrait: float, dz: float) -> Forme:
        haut = tr.pts[-1]
        z_haut = haut[0, 2]
        n_chanf = max(int(np.ceil(retrait / dz)), 1)       # chanfrein à 45° (Δz = Δr)
        n_col = max(int(np.ceil(self.hauteur_col / dz)), 1)
        couches = []
        for i in range(1, n_chanf + n_col + 1):
            d = -retrait * min(i / n_chanf, 1.0)
            z = z_haut + i * retrait / n_chanf if i <= n_chanf else \
                z_haut + retrait + (i - n_chanf) * self.hauteur_col / n_col
            c = decaler_contour(haut[:, :2], d)
            couches.append(np.concatenate([c, np.full((len(c), 1), z)], axis=1))
        return tr.copie(pts=np.concatenate([tr.pts, np.array(couches)], axis=0))


@dataclass
class Reseau(Emboitement):
    """Grille de copies, avec rotation et échelle progressives."""

    colonnes: int = param(3, 1, 8, 1, "colonnes")
    lignes: int = param(1, 1, 8, 1, "lignes")
    espacement: float = param(10.0, 0, 80, 1, "espace entre pièces (mm)")
    rotation_pas: float = param(15.0, -180, 180, 5, "rotation ajoutée à chaque copie (degrés)")
    echelle_pas: float = param(0.0, -0.3, 0.3, 0.01, "variation d'échelle par copie")

    def appliquer(self, forme):
        mn, mx = forme.boite()
        taille = (mx[:2] - mn[:2]).max()
        pas = taille * (1 + abs(self.echelle_pas) * self.colonnes * self.lignes) + self.espacement
        centre = forme.centres()[0]
        pieces = []
        i = 0
        for l in range(int(self.lignes)):
            for c in range(int(self.colonnes)):
                p = forme.copie()
                d = p.pts[:, :, :2] - centre
                s = max(1 + self.echelle_pas * i, 0.1)
                a = np.radians(self.rotation_pas * i)
                ca, sa = np.cos(a), np.sin(a)
                p.pts[:, :, 0] = centre[0] + s * (d[..., 0] * ca - d[..., 1] * sa) + c * pas
                p.pts[:, :, 1] = centre[1] + s * (d[..., 0] * sa + d[..., 1] * ca) + l * pas
                p.pts[:, :, 2] *= s
                p.nom = f"copie-{i + 1}"
                pieces.append(p)
                i += 1
        # recentrer la grille
        mn, mx = Assemblage(pieces).boite()
        dx, dy = centre - (mn[:2] + mx[:2]) / 2
        return Assemblage([p.translater(dx, dy) for p in pieces])



@dataclass
class Couvercle(Emboitement):
    """Ajoute un couvercle ajusté à l'ouverture de la forme.

    Le couvercle est un plateau (contour du sommet élargi de ``debord``) prolongé
    par un col qui entre dans l'ouverture, rétréci de ``paroi + jeu``.
    Il est montré en place, au-dessus de la forme ; pour l'impression (G-code,
    STL) il est retourné : plateau sur le plateau d'impression, col vers le haut.
    Pour un plateau plein, gardez ``epaisseur`` ≤ couches_fond × hauteur_couche.
    """

    epaisseur: float = param(0.8, 0.2, 5, 0.1, "épaisseur du plateau (mm)")
    debord: float = param(1.0, -5, 10, 0.5, "débord du plateau au-delà de la paroi (mm)")
    hauteur_col: float = param(6.0, 0, 30, 0.5, "hauteur du col (mm, 0 = sans col)")
    paroi: float = param(0.8, 0.4, 4, 0.1, "épaisseur de paroi imprimée (mm)")
    jeu: float = param(0.3, 0.05, 2, 0.05, "jeu d'emboîtement (mm)")
    ecart_vue: float = param(15.0, 0, 80, 1, "écart vertical dans la vue (mm)")

    def appliquer(self, forme):
        haut = forme.pts[-1, :, :2]
        z = forme.z[-1] + self.ecart_vue
        couches = []                                         # vue : col en bas, plateau en haut
        if self.hauteur_col > 0:
            col = decaler_contour(haut, -(self.paroi + self.jeu))
            couches += [(col, z - self.hauteur_col), (col, z)]
        plateau = decaler_contour(haut, self.debord)
        z_plateau = z + 1e-3 if couches else z               # marche quasi horizontale col → plateau
        couches += [(plateau, z_plateau), (plateau, z_plateau + self.epaisseur)]
        pts = np.array([np.column_stack([c, np.full(len(c), zc)]) for c, zc in couches])
        couvercle = Forme(pts, nom="couvercle", fond=False, ferme_haut=True, retournee=True)
        return Assemblage([forme.copie(), couvercle])


TOUS = [Gigogne, Empilement, Reseau, Couvercle]
