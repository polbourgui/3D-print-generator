"""Dentelle verticale imprimée en fil (« wire printing », non planaire).

Principe (celui de WirePrint et du « Wire Printing » de Cura) : la paroi est un
treillis d'étages. Chaque étage part d'un **anneau** horizontal déjà imprimé :

1. **montée** lente d'un nœud de l'anneau vers un sommet, au niveau de l'étage
   suivant, avec une légère surélévation (``affaissement``) et une **pause**
   pour que le brin fige en l'air ;
2. **descente** en diagonale vers le nœud suivant de l'anneau du dessous ;
3. une fois le tour fait, impression de l'**anneau** de l'étage suivant, qui
   relie les sommets : c'est la base sur laquelle l'étage d'après se pose.

Un brin tiré dans le vide se tend en ligne droite entre ses deux appuis : tout
le trajet est donc fait de **segments droits** entre des nœuds situés sur la
surface de la forme (pas d'arcs, qui s'aplatiraient et passeraient à
l'intérieur de la forme).

Motifs :
- ``triangles`` : montées verticales, descentes en diagonale (le plus rigide) ;
- ``losanges``  : montées et descentes en diagonale ; les nœuds se décalent
  d'une demi-maille à chaque étage, ce qui dessine des losanges.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometrie import Forme, Module, param

MOTIFS = ("losanges", "triangles")

# types de mouvement → attribut de vitesse
VITESSES = {"bord": "vitesse_anneau", "anneau": "vitesse_anneau", "montee_lente": "vitesse_montee",
            "montee": "vitesse_montee", "descente": "vitesse_descente"}
EN_FIL = {"anneau", "montee_lente", "montee", "descente"}       # brins tirés dans le vide


def _point_surface(forme: Forme, indice: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Point (x, y) de la surface à l'indice de contour (réel) et à la hauteur z."""
    indice, z = np.atleast_1d(indice).astype(float), np.atleast_1d(z).astype(float)
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
    """Paroi ajourée en treillis, imprimée en fil (G-code uniquement).

    Une maille fait périmètre / ``cellules`` de large et ``hauteur_maille`` de
    haut (un étage) ; elle peut évoluer jusqu'à ``maille_haut`` au sommet.
    Diagonales conseillées entre 35° et 65° : plus couchées elles s'affaissent,
    plus raides la buse risque d'accrocher le brin voisin.
    """

    motif: str = param("losanges", aide="forme des mailles", choix=MOTIFS)
    cellules: int = param(24, 4, 96, 1, "mailles sur le tour")
    hauteur_maille: float = param(4.0, 1.5, 20, 0.5, "hauteur d'un étage en bas (mm)")
    maille_haut: float = param(0.0, 0, 20, 0.5, "hauteur d'un étage en haut (mm, 0 = identique)")
    bord_bas: float = param(3.0, 0, 40, 0.5, "bord plein en bas, au-dessus du fond (mm)")
    bord_haut: float = param(3.0, 0, 40, 0.5, "bord plein en haut (mm)")
    vitesse_montee: float = param(4.0, 1, 20, 0.5, "vitesse des montées dans le vide (mm/s)")
    vitesse_descente: float = param(6.0, 1, 30, 0.5, "vitesse des descentes (mm/s)")
    vitesse_anneau: float = param(5.0, 2, 40, 1, "vitesse des anneaux et des bords (mm/s)")
    pause: float = param(0.5, 0, 3, 0.1, "pause au sommet de chaque montée (s)")
    affaissement: float = param(0.5, 0, 3, 0.1, "surélévation des sommets (mm), compense l'affaissement")
    pression: float = param(0.3, 0, 1, 0.05, "enfoncement de l'anneau dans les sommets (mm)")
    pause_noeud: float = param(0.2, 0, 2, 0.05, "pause à chaque soudure (sommet de l'anneau, pose d'une descente) (s)")
    debit_fil: float = param(0.85, 0.5, 1.2, 0.05, "débit des brins tirés dans le vide (× débit normal)")

    def __post_init__(self):
        if self.motif not in MOTIFS:          # anciens réglages (zigzag, alvéoles…)
            self.motif = "losanges"

    # ------------------------------------------------------------------ géométrie
    def _etages_z(self, z0: float, z_haut: float):
        """Hauteurs des anneaux successifs, de z0 jusque sous le bord du haut."""
        m_haut = self.maille_haut or self.hauteur_maille
        zs = [z0]
        while True:
            t = (zs[-1] - z0) / max(z_haut - z0, 1e-9)
            pas = self.hauteur_maille + (m_haut - self.hauteur_maille) * t
            if zs[-1] + pas > z_haut - self.bord_haut + 1e-9:
                return zs
            zs.append(zs[-1] + pas)

    def trajet(self, forme: Forme, h: float, z_debut: float | None = None, largeur_ligne: float = 0.45):
        """Liste d'étages ; chaque étage est une liste de mouvements (type, points (k, 3), pause).

        Le premier point est sur la surface, à l'indice 0, à ``z_debut`` (dessus du fond).
        """
        L, N, _ = forme.pts.shape
        z_haut = float(forme.z[-1])
        z0 = float(forme.z[0]) if z_debut is None else float(z_debut)
        n = int(self.cellules)
        etages = []

        def surf(angle, z):
            angle, z = np.broadcast_arrays(np.asarray(angle, float), np.asarray(z, float))
            return np.column_stack([_point_surface(forme, angle / (2 * np.pi) * N, z), z])

        # 1. bord du bas : spirale classique sur la surface, h par tour
        tours = int(np.ceil(max(self.bord_bas, 0) / h - 1e-9))
        a = np.linspace(0, 2 * np.pi, N + 1)          # chaque tour inclut son point de départ
        for k in range(tours):
            pts = surf(a, z0 + h * (k + a / (2 * np.pi)))
            etages.append([("bord", pts, 0.0)])
        Z = self._etages_z(z0 + tours * h, z_haut)

        # 2. étages du treillis
        decal = 0.0                                   # décalage des nœuds (en mailles)
        demi = np.pi / n
        fall = np.array([0.0, 0.0, self.affaissement])
        for k in range(len(Z) - 1):
            za, zb = Z[k], Z[k + 1]
            noeuds = 2 * np.pi * (np.arange(n + 1) + decal) / n
            sommets = noeuds + (demi if self.motif == "losanges" else 0.0)
            V = surf(noeuds, za)
            T = surf(sommets, zb)
            # l'anneau du dessous a été imprimé plus bas de « pression » (sauf sur le bord plein)
            if k > 0:
                V[:, 2] -= self.pression
            # le dernier retour se pose juste avant le nœud 0 (à ~2 largeurs de ligne),
            # d'où une montée de raccord vers l'anneau qui ne touche aucun brin existant
            eps = 2 * largeur_ligne
            frac_v = 1 - eps / max(np.linalg.norm(V[n, :2] - V[n - 1, :2]), 1e-9)
            frac_t = 1 - eps / max(np.linalg.norm(T[n, :2] - T[n - 1, :2]), 1e-9)
            Lp = V[n - 1] + frac_v * (V[n] - V[n - 1])
            W = T[n - 1] + frac_t * (T[n] - T[n - 1])
            mvts = []

            def monter(depart, sommet):
                # début en douceur (1/5 à demi-vitesse), puis pause au sommet pour figer le brin
                relais = depart + 0.2 * (sommet - depart)
                mvts.append(("montee_lente", np.array([depart, relais]), 0.0))
                mvts.append(("montee", np.array([relais, sommet]), self.pause))

            for i in range(n):
                monter(V[i], T[i] + fall)
                fin = Lp if i == n - 1 else V[i + 1]
                mvts.append(("descente", np.array([T[i] + fall, fin]), self.pause_noeud))
            monter(Lp, W + fall)
            # anneau : relie tous les sommets, enfoncé de « pression » et soudé à chacun
            # (pause) pour ne pas se rétracter comme un élastique ; il se termine sur le
            # sommet 0, premier nœud de l'étage suivant
            bas = np.array([0.0, 0.0, -self.pression])
            prec = W + fall
            for cible in [W, *T[:n], W, T[0]]:
                mvts.append(("anneau", np.array([prec, cible + bas]), self.pause_noeud))
                prec = cible + bas
            etages.append(mvts)
            if self.motif == "losanges":
                decal += 0.5

        # 3. bord du haut : spirale sur le polygone du dernier anneau (cordes, comme lui)
        abaisse = self.pression if len(Z) > 1 else 0.0
        z = Z[-1] - abaisse
        noeuds = 2 * np.pi * (np.arange(n + 1) + decal) / n
        sous = max(int(np.ceil(N / n)), 2)            # points par corde (montée régulière)
        while z < z_haut - 1e-9:
            dz = min(h, z_haut - z)
            def coin(i, zz):                            # xy pris au niveau nominal de l'anneau
                c = surf(noeuds[i:i + 1], zz + abaisse)
                c[:, 2] -= abaisse
                return c

            pts = [coin(0, z)]                          # point de départ du tour
            for i in range(n):
                s = np.arange(1, sous + 1) / sous
                zz = z + dz * (i + s) / n
                A, B = coin(i, zz), coin(i + 1, zz)
                pts.append(A + s[:, None] * (B - A))
            etages.append([("bord", np.vstack(pts), 0.0)])
            z += dz
        return etages

    def points(self, etages) -> np.ndarray:
        """Trajet complet (M, 3), pour l'aperçu."""
        return np.vstack([p for e in etages for _, p, _ in e])

    def vitesse(self, type_: str) -> float:
        v = getattr(self, VITESSES[type_])
        return v / 2 if type_ == "montee_lente" else v

    def debit(self, type_: str) -> float:
        return self.debit_fil if type_ in EN_FIL else 1.0

    def resume(self, forme: Forme, h: float) -> dict:
        """Dimensions d'une maille et angle des diagonales (pour l'interface)."""
        c = forme.pts[len(forme.pts) // 2, :, :2]
        perimetre = float(np.linalg.norm(np.diff(c, axis=0, append=c[:1]), axis=1).sum())
        largeur = perimetre / int(self.cellules)
        hauteur = max(self.hauteur_maille, self.maille_haut or 0)
        portee = largeur / 2 if self.motif == "losanges" else largeur
        angles = [np.degrees(np.arctan2(m, portee)) for m in (self.hauteur_maille, hauteur)]
        etages = max(len(self._etages_z(float(forme.z[0]) + self.bord_bas, float(forme.z[-1]))) - 1, 0)
        return {"largeur": largeur, "hauteur": self.hauteur_maille, "etages": etages,
                "angle_min": float(min(angles)), "angle_max": float(max(angles))}
