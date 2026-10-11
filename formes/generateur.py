"""Pipeline : base → déformations (dans l'ordre) → emboîtement éventuel."""

from __future__ import annotations

from dataclasses import dataclass, field

from .bases import Base
from .deformations import Deformation
from .emboitements import Emboitement
from .geometrie import Assemblage, Forme


@dataclass
class Generateur:
    base: Base = field(default_factory=Base)
    deformations: list[Deformation] = field(default_factory=list)
    emboitement: Emboitement | None = None

    # -- activation des modules --------------------------------------------
    def module(self, nom: str):
        """Retrouve un module par son nom de classe (insensible à la casse)."""
        for m in [*self.deformations, self.emboitement]:
            if m is not None and m.nom.lower() == nom.lower():
                return m
        raise KeyError(nom)

    def activer(self, *noms: str, actif: bool = True) -> "Generateur":
        for n in noms:
            self.module(n).actif = actif
        return self

    def desactiver(self, *noms: str) -> "Generateur":
        return self.activer(*noms, actif=False)

    # -- génération --------------------------------------------------------------
    def forme(self) -> Forme:
        f = self.base.construire()
        for d in self.deformations:
            if d.actif:
                f = d.appliquer(f)
        return f

    def generer(self) -> Assemblage:
        f = self.forme()
        if self.emboitement is not None and self.emboitement.actif:
            return self.emboitement.appliquer(f)
        return Assemblage([f])

    def __repr__(self):
        lignes = [f"Base({self.base.profil}, r={self.base.rayon:g}, h={self.base.hauteur:g})"]
        lignes += [f"  {d!r}" for d in self.deformations]
        if self.emboitement is not None:
            lignes.append(f"  {self.emboitement!r}")
        return "\n".join(lignes)
