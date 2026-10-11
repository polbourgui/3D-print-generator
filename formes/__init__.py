"""Générateur de formes abstraites : base + modules de déformation + emboîtements,
avec export en visualisation 3D (HTML), STL et G-code."""

from .geometrie import Forme, Assemblage
from .bases import Base
from .deformations import (
    Torsion, Fuseau, Ondulation, Plis, Bruit, Courbure, Pincement,
)
from .emboitements import Gigogne, Empilement, Reseau
from .generateur import Generateur
from .gcode import ParametresImpression, generer_gcode, exporter_gcode
from .visualisation import figure_3d, figure_trajet, exporter_html

__all__ = [
    "Forme", "Assemblage", "Base",
    "Torsion", "Fuseau", "Ondulation", "Plis", "Bruit", "Courbure", "Pincement",
    "Gigogne", "Empilement", "Reseau",
    "Generateur",
    "ParametresImpression", "generer_gcode", "exporter_gcode",
    "figure_3d", "figure_trajet", "exporter_html",
]
