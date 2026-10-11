"""Visualisation 3D interactive (Plotly) : maillage des pièces et trajet G-code."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .geometrie import Assemblage, Forme

PALETTE = ["#e8b04a", "#4aa3e8", "#e8574a", "#5fc28a", "#b07ae8", "#e87ab9", "#9aa0a6", "#4ae0d2"]
COULEURS_TRAJET = {
    "spirale": "#e8b04a", "perimetre": "#e8b04a", "remplissage": "#4aa3e8",
    "deplacement": "rgba(150,150,150,0.35)", "purge": "#5fc28a",
}


def _go():
    try:
        import plotly.graph_objects as go
    except ImportError as e:  # pragma: no cover
        raise ImportError("plotly est requis : pip install plotly") from e
    return go


def _scene(fig, titre):
    fig.update_layout(
        title=titre,
        scene=dict(aspectmode="data", xaxis_title="x (mm)", yaxis_title="y (mm)", zaxis_title="z (mm)",
                   camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9))),
        margin=dict(l=0, r=0, t=40, b=0),
        template="plotly_dark", height=650,
    )
    return fig


def figure_3d(assemblage: Assemblage | Forme, titre: str = "Forme", aretes: bool = False):
    """Maillage ombré de chaque pièce (une couleur par pièce)."""
    go = _go()
    if isinstance(assemblage, Forme):
        assemblage = Assemblage([assemblage])
    fig = go.Figure()
    for i, p in enumerate(assemblage):
        v, f = p.maillage()
        fig.add_trace(go.Mesh3d(
            x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2],
            color=PALETTE[i % len(PALETTE)], name=p.nom, showlegend=len(assemblage) > 1,
            flatshading=False, opacity=1.0,
            lighting=dict(ambient=0.35, diffuse=0.8, specular=0.4, roughness=0.5, fresnel=0.2),
            lightposition=dict(x=100, y=-200, z=300),
        ))
        if aretes:
            pas = max(p.pts.shape[0] // 40, 1)
            for c in p.pts[::pas]:
                b = np.vstack([c, c[:1]])
                fig.add_trace(go.Scatter3d(x=b[:, 0], y=b[:, 1], z=b[:, 2], mode="lines",
                                           line=dict(color="black", width=1), showlegend=False,
                                           hoverinfo="skip"))
    return _scene(fig, titre)


def figure_trajet(trajet, titre: str = "Trajet G-code", deplacements: bool = False,
                  max_points: int = 200_000):
    """Trajet d'outil coloré par type (spirale/périmètre, remplissage, purge...)."""
    go = _go()
    fig = go.Figure()
    par_type: dict[str, list] = {}
    for type_, pts in trajet.segments:
        if type_ == "deplacement" and not deplacements:
            continue
        par_type.setdefault(type_, []).append(pts)
    for type_, morceaux in par_type.items():
        # concaténation avec des NaN pour couper les lignes entre morceaux
        nan = np.full((1, 3), np.nan)
        pts = np.vstack([x for m in morceaux for x in (m, nan)])
        if len(pts) > max_points:
            pts = pts[:: int(np.ceil(len(pts) / max_points))]
        fig.add_trace(go.Scatter3d(
            x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode="lines", name=type_,
            line=dict(color=COULEURS_TRAJET.get(type_, "white"), width=2),
        ))
    return _scene(fig, titre)


def exporter_html(fig, chemin) -> Path:
    """Exporte une figure en page HTML autonome (ouvrable sans Python)."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(chemin, include_plotlyjs="cdn", full_html=True)
    return chemin
