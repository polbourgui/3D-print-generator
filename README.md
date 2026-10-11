# Générateur de formes abstraites

Notebook Jupyter pour composer des formes abstraites à partir d'une **forme de base**,
de **modules de déformation** activables et d'un **emboîtement** optionnel, puis les
exporter en **visualisation 3D** (HTML interactif), **STL** et **G-code**.

> Ce dossier est indépendant du site vitrine et exclu de son déploiement (`.assetsignore`).

## Installation

```bash
cd generateur-formes
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab generateur_formes.ipynb
```

## Principe

Une forme est une pile de contours horizontaux fermés (`pts` : couches × points × 3).
Cette représentation colle directement au fonctionnement d'une imprimante FDM, ce qui
rend la génération du G-code simple et fiable.

```
Base ──► Fuseau ──► Torsion ──► Ondulation ──► … ──► Emboîtement ──► Assemblage
                 (chaque module : actif=True/False)                    │
                                         ┌──────────────┬──────────────┼──────────────┐
                                     figure_3d       STL          G-code       figure_trajet
```

| Catégorie | Modules |
|---|---|
| Base | `cercle`, `polygone`, `etoile`, `superellipse`, `goutte` |
| Déformations | `Fuseau`, `Torsion`, `Ondulation`, `Plis`, `Bruit`, `Pincement`, `Courbure` |
| Emboîtements | `Gigogne` (coques imbriquées imprimables en place), `Empilement` (modules à col d'emboîtement, chanfrein 45°), `Reseau` (grille) |

### G-code

- `mode="spirale"` : mode vase, Z continu, sans couture (une seule pièce).
- `mode="couches"` : plusieurs pièces par couche avec rétractions ; utilisé automatiquement
  pour les assemblages.
- Fond plein (périmètre + remplissage croisé) sur `couches_fond` couches pour les pièces
  qui en ont un.
- Avertissements : dépassement du plateau ou de la hauteur max, surplombs > 50°.
- Dialecte Marlin, extrusion absolue : adaptez températures, plateau et vitesses dans
  `ParametresImpression`.

## Utilisation en script

```python
from formes import *

gen = Generateur(
    Base(profil="polygone", cotes=7, rayon=35, hauteur=90),
    [Fuseau(echelle_haut=0.6), Torsion(angle=180), Plis(actif=False)],
    Gigogne(nombre=3),
)
assemblage = gen.generer()
exporter_html(figure_3d(assemblage), "sorties/vase.html")
assemblage.exporter_stl("sorties/vase.stl")
exporter_gcode(assemblage, "sorties/vase.gcode", ParametresImpression(mode="couches"))
```

## Ajouter un module

Dans `formes/deformations.py` :

```python
@dataclass
class MaDeformation(Deformation):
    force: float = param(1.0, 0, 10, 0.1, "intensité")

    def appliquer(self, forme):
        f = forme.copie()
        f.pts[:, :, 0] *= 1 + 0.01 * self.force * forme.t()   # ne modifier que x et y
        return f
```

Le panneau interactif du notebook (`formes.interface.panneau`) génère ses curseurs
automatiquement à partir des `param(...)`.

## Tests

```bash
pip install pytest
python -m pytest tests
```
