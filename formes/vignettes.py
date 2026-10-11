"""Vignettes PNG intégrées au G-code (aperçu Mainsail, Fluidd, KlipperScreen).

Format « PrusaSlicer », reconnu par Moonraker :

    ; thumbnail begin 300x300 12345
    ; iVBORw0KGgo...            (base64, lignes de 78 caractères max)
    ; thumbnail end

Le rendu est fait avec matplotlib (sans fenêtre), en sur-échantillonnage
puis réduit par moyenne, sur fond transparent.
"""

from __future__ import annotations

import base64
import io

import numpy as np

from .geometrie import Forme

COULEURS = ["#e8b04a", "#4aa3e8", "#e8574a", "#5fc28a", "#b07ae8", "#e87ab9"]


def _alleger(f: Forme, couches: int = 70, points: int = 140) -> Forme:
    L, N, _ = f.pts.shape
    il = np.unique(np.r_[np.linspace(0, L - 1, min(L, couches)).round().astype(int), L - 1])
    ip = np.linspace(0, N, min(N, points), endpoint=False).astype(int)
    return f.copie(pts=f.pts[il][:, ip])


def rendu_rgba(pieces: list[Forme], taille: int = 600) -> np.ndarray:
    """Image RGBA (taille × taille, valeurs 0..1) des pièces vues en 3/4."""
    import matplotlib
    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import LightSource
    from matplotlib.figure import Figure
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    fig = Figure(figsize=(taille / 100, taille / 100), dpi=100)
    fig.patch.set_alpha(0)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1], projection="3d")
    ax.set_axis_off()
    ax.patch.set_alpha(0)
    ax.view_init(elev=25, azim=-60)
    ls = LightSource(azdeg=225, altdeg=40)
    mins, maxs = [], []
    for i, q in enumerate(pieces):
        v, f = _alleger(q).maillage()
        ax.add_collection3d(Poly3DCollection(v[f], facecolors=COULEURS[i % len(COULEURS)],
                                             edgecolor="none", shade=True, lightsource=ls))
        mins.append(v.min(0))
        maxs.append(v.max(0))
    mn, mx = np.min(mins, 0), np.max(maxs, 0)
    c, r = (mn + mx) / 2, (mx - mn).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1), zoom=1.35)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba(), dtype=float) / 255


def _reduire(img: np.ndarray, n: int) -> np.ndarray:
    """Réduction par moyenne de blocs, pondérée par l'alpha (pas de halo)."""
    m = img.shape[0]
    if m < n:
        idx = (np.arange(n) * m / n).astype(int)
        return img[idx][:, idx]
    bornes = np.linspace(0, m, n + 1).astype(int)[:-1]
    a = img[..., 3:4]
    premult = np.concatenate([img[..., :3] * a, a], axis=-1)
    somme = np.add.reduceat(np.add.reduceat(premult, bornes, axis=0), bornes, axis=1)
    taille = np.diff(np.r_[bornes, m])
    somme /= (taille[:, None] * taille[None, :])[..., None]
    alpha = somme[..., 3:4]
    rgb = np.where(alpha > 0, somme[..., :3] / np.maximum(alpha, 1e-9), 0)
    return np.clip(np.concatenate([rgb, alpha], axis=-1), 0, 1)


def _recadrer(img: np.ndarray) -> np.ndarray:
    """Recadre au plus juste autour de la forme (carré, petite marge)."""
    ys, xs = np.nonzero(img[..., 3] > 0.02)
    if not len(xs):
        return img
    c = np.array([(ys.min() + ys.max()) / 2, (xs.min() + xs.max()) / 2])
    r = int(max(ys.max() - ys.min(), xs.max() - xs.min()) / 2 * 1.08) + 1
    pad = np.pad(img, ((r, r), (r, r), (0, 0)))
    y0, x0 = (c + r).astype(int) - r
    return pad[y0:y0 + 2 * r, x0:x0 + 2 * r]


def png(img: np.ndarray, largeur: int, hauteur: int) -> bytes:
    """Encode une image carrée en PNG largeur × hauteur (centrée, fond transparent)."""
    from matplotlib.image import imsave

    cote = min(largeur, hauteur)
    petit = _reduire(img, cote)
    toile = np.zeros((hauteur, largeur, 4))
    y0, x0 = (hauteur - cote) // 2, (largeur - cote) // 2
    toile[y0:y0 + cote, x0:x0 + cote] = petit
    tampon = io.BytesIO()
    imsave(tampon, toile, format="png")
    return tampon.getvalue()


def vignettes_gcode(pieces: list[Forme], tailles=((32, 32), (300, 300))) -> list[str]:
    """Lignes de commentaires G-code contenant les vignettes PNG en base64."""
    img = _recadrer(rendu_rgba(pieces, min(4 * max(max(t) for t in tailles), 1200)))
    lignes = []
    for l, h in tailles:
        b64 = base64.b64encode(png(img, l, h)).decode()
        lignes.append(f"; thumbnail begin {l}x{h} {len(b64)}")
        lignes += [f"; {b64[i:i + 78]}" for i in range(0, len(b64), 78)]
        lignes.append("; thumbnail end")
        lignes.append(";")
    return lignes[:-1]
