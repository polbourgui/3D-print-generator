"""Générateur de formes abstraites : base + modules de déformation + emboîtements,
avec export en visualisation 3D (HTML), STL et G-code (Klipper ou Marlin)."""

from .geometrie import Forme, Assemblage
from .bases import Base
from .deformations import (
    Torsion, Fuseau, Ondulation, Plis, Bruit, Courbure, Pincement,
    Nervures, Losanges, Ecailles, Facettes, Bec,
)
from .emboitements import Gigogne, Empilement, Reseau, Couvercle, Luminaire
from .generateur import Generateur
from .gcode import VERSION, ParametresImpression, generer_gcode, exporter_gcode
from .visualisation import figure_3d, figure_trajet, exporter_html

__all__ = [
    "Forme", "Assemblage", "Base",
    "Torsion", "Fuseau", "Ondulation", "Plis", "Bruit", "Courbure", "Pincement",
    "Nervures", "Losanges", "Ecailles", "Facettes", "Bec",
    "Gigogne", "Empilement", "Reseau", "Couvercle", "Luminaire",
    "Generateur",
    "VERSION", "ParametresImpression", "generer_gcode", "exporter_gcode",
    "figure_3d", "figure_trajet", "exporter_html",
]
