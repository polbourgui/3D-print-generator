"""Générateur de formes abstraites : base + modules de déformation + emboîtements,
avec export en visualisation 3D (HTML), STL et G-code (Klipper ou Marlin).

Plus des plaques de test pour régler un filament (``formes.plaques``)."""

from .geometrie import Forme, Assemblage
from .bases import Base
from .deformations import (
    Torsion, Fuseau, Ondulation, Plis, Bruit, Courbure, Pincement,
    Nervures, Losanges, Ecailles, Facettes, Bec,
)
from .emboitements import Gigogne, Empilement, Reseau, Couvercle, Luminaire
from .dentelle import Dentelle
from .generateur import Generateur
from .gcode import VERSION, ParametresImpression, generer_gcode, exporter_gcode
from .visualisation import figure_3d, figure_trajet, exporter_html
from .plaques import (PETG_ARIANEPLAST, Plaques, ReglagePlaque, plan, serie, exporter_plaques,
                      exporter_stl_plaques, exporter_fiche, figure_plaques)

__all__ = [
    "Forme", "Assemblage", "Base",
    "Torsion", "Fuseau", "Ondulation", "Plis", "Bruit", "Courbure", "Pincement",
    "Nervures", "Losanges", "Ecailles", "Facettes", "Bec",
    "Gigogne", "Empilement", "Reseau", "Couvercle", "Luminaire",
    "Dentelle",
    "Generateur",
    "VERSION", "ParametresImpression", "generer_gcode", "exporter_gcode",
    "figure_3d", "figure_trajet", "exporter_html",
    "PETG_ARIANEPLAST", "Plaques", "ReglagePlaque", "plan", "serie", "exporter_plaques",
    "exporter_stl_plaques", "exporter_fiche", "figure_plaques",
]
