# Générateur de formes abstraites

Notebook Jupyter pour composer des formes abstraites à partir d'une **forme de base**,
de **modules de déformation** activables et d'un **emboîtement** optionnel, puis les
exporter en **visualisation 3D** (HTML interactif), **STL** et **G-code Klipper**
(aperçu Mainsail, métadonnées Moonraker, exclude object, compatible KAMP) ou Marlin.

## Installation

**Windows, le plus simple :** téléchargez le dépôt (bouton vert **Code → Download ZIP** sur
GitHub, puis extrayez-le) ou clonez-le, et **double-cliquez sur `Lancer.bat`**. La première
fois, il crée l'environnement Python et installe les dépendances (quelques minutes) ; ensuite
il ouvre directement l'application dans le navigateur.

Ou bien, une seule ligne à copier-coller : elle clone le dépôt, crée l'environnement virtuel
`.venv`, installe les dépendances et ouvre l'application dans le navigateur.

**Windows (PowerShell)**

```powershell
git clone https://github.com/polbourgui/3D-print-generator.git; cd 3D-print-generator; python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt; .venv\Scripts\python lancer.py
```

**Linux / macOS**

```bash
git clone https://github.com/polbourgui/3D-print-generator.git && cd 3D-print-generator && python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt && .venv/bin/python lancer.py
```

Les commandes appellent directement le Python du `.venv` : pas besoin de l'activer
(ni de modifier la politique d'exécution des scripts sous Windows).

### Relancer plus tard

Depuis le dossier `3D-print-generator` (remplacez `.venv\Scripts\python` par
`.venv/bin/python` sous Linux / macOS) :

| commande | ce qui s'ouvre |
|---|---|
| double-clic sur `Lancer.bat`, ou `.venv\Scripts\python lancer.py` | l'application seule, sans code, le navigateur s'ouvre tout seul |
| `.venv\Scripts\python -m jupyter lab generateur_formes.ipynb` | la même application dans Jupyter Lab (menu **Run → Run All Cells**) |
| `.venv\Scripts\python -m jupyter lab generateur_formes_script.ipynb` | la version en code |

Pour arrêter : **Ctrl + C** dans le terminal, ou fermez sa fenêtre.
Si le navigateur ne s'ouvre pas, copiez l'adresse affichée dans le terminal (`http://localhost:8866/`).

## Application

Tout se règle à la souris, sans saisie :

| onglet | contenu |
|---|---|
| **Forme** | profil de base (menu déroulant) et dimensions ; seuls les réglages utiles au profil sont affichés |
| **Déformations** | une case pour activer chaque module, ses curseurs, ↑ / ↓ pour l'ordre d'application |
| **Emboîtement** | boutons radio : aucun, gigogne, empilement, réseau, couvercle, luminaire |
| **Dentelle** | paroi ajourée en filet, imprimée en non planaire : motif (losanges, zigzag, alvéoles), mailles, bords pleins, pièce de calibration |
| **Réglages** | trois pages comme dans un trancheur : **Imprimante** (modèle préréglé, firmware, plateau, hauteur max, buse, vitesse Z, vignettes, options Klipper : macros, purge KAMP, maillage adaptatif, exclude object, rétraction firmware), **Filament** (profils PLA, PETG, PETG transparent Arianeplast, ABS, ASA, TPU et profils enregistrés ; nom, type, couleur, Ø, densité, prix ; températures buse et plateau, dont 1re couche ; ventilateur et couches sans ventilation ; multiplicateur de débit ; rétraction, seuil, z-hop), **Impression** (mode spirale / couches, hauteurs de 1re couche et de couche, largeur de ligne, couches de fond, vitesses) |
| **Plaques** | plaques de test 35 × 70 mm pour régler un filament (PETG transparent Arianeplast), une série de réglages par plaque, gravés en empreinte dans le bas de la pièce ; G-code, STL et fiche d'évaluation |
| **Export** | HTML, STL et G-code en un clic, trajet G-code, ouverture du dossier `sorties/`, sauvegarde et chargement des réglages |

En haut : **Aperçu** (Rapide / Normal / Fin) règle la finesse de la vue pendant les
réglages (les exports utilisent toujours la résolution de l'onglet Forme), et
**Surprise** tire une combinaison de déformations au hasard. Au-dessus de la vue,
l'encombrement et les alertes (plateau, hauteur, surplombs) se mettent à jour en direct.

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
| Base | `cercle`, `polygone`, `etoile`, `superellipse`, `goutte`, `fleur`, `engrenage` |
| Déformations | `Fuseau`, `Torsion`, `Ondulation`, `Plis`, `Bruit`, `Pincement`, `Courbure`, `Nervures`, `Losanges`, `Ecailles`, `Facettes`, `Bec` |
| Emboîtements | `Gigogne` (coques imbriquées imprimables en place), `Empilement` (modules à col d'emboîtement, chanfrein 45°), `Reseau` (grille), `Couvercle` (couvercle à col, retourné automatiquement pour l'impression), `Luminaire` (abat-jour : fond percé pour douille E27 / E14 / GU10, suspension ou à poser) |

### Luminaires et abats-jour

`Luminaire` remplace le fond (ou le dessus) par une **couronne percée** pour la douille ; la
couronne se serre entre la douille et sa bague filetée.

| culot | perçage (avant jeu) |
|---|---|
| E27 (douille à bague filetée) | Ø 40 mm |
| E14 (douille à bague filetée) | Ø 28 mm |
| GU10 / MR16 (passage du spot) | Ø 50 mm |
| perso | réglable |

Ces cotes sont les plus courantes : mesurez votre douille au pied à coulisse et passez en
« perso » si elle diffère.

- **suspension** : douille en haut, bas ouvert ; la pièce est retournée pour l'impression
  (couronne sur le plateau), ce qui reste compatible avec le mode vase.
- **à poser** : douille au fond.
- **manchon** (optionnel) : tube de centrage autour du perçage ; impose le mode couches.
- L'épaisseur de la couronne vaut `couches_fond × hauteur_couche` : visez au moins 1,2 mm.
- Ampoules **LED uniquement** : le PLA ramollit vers 60 °C (PETG ≈ 80 °C).

### Dentelle (impression en fil, non planaire)

La paroi devient un **treillis** imprimé dans le vide, étage par étage, selon le principe de
WirePrint et du « Wire Printing » de Cura :

1. **montée** lente d'un nœud de l'anneau vers un sommet, au niveau de l'étage suivant, avec
   une légère surélévation (`affaissement`) et une **pause** pour que le brin fige ;
2. **descente** en diagonale vers le nœud suivant de l'anneau du dessous ;
3. **anneau** horizontal reliant tous les sommets : c'est l'appui de l'étage suivant.

Un brin tiré dans le vide se tend en ligne droite entre ses deux appuis : le trajet n'est fait
que de **segments droits** entre des nœuds placés sur la surface de la forme.

| réglage | effet |
|---|---|
| `motif` | `losanges` (montées et descentes en diagonale, nœuds décalés d'une demi-maille à chaque étage) ou `triangles` (montées verticales, le plus rigide) |
| `cellules` | mailles sur le tour (largeur = périmètre / cellules) |
| `hauteur_maille`, `maille_haut` | hauteur d'un étage en bas et en haut |
| `bord_bas`, `bord_haut` | bords pleins |
| `vitesse_montee`, `vitesse_descente`, `vitesse_anneau` | lentes : 4, 6 et 8 mm/s par défaut |
| `pause`, `affaissement` | pause au sommet (s) et surélévation des sommets (mm) |
| `pression`, `pause_noeud` | enfoncement de l'anneau dans les sommets (mm) et pause à chaque soudure (s) |
| `debit_fil` | débit des brins tirés dans le vide (0,85 par défaut) |
| `angle_buse` | angle maximal des descentes (40° par défaut), voir ci-dessous |

- **Dégagement de la buse** : pendant une descente, le brin reste tendu entre la buse et le
  sommet d'où elle vient ; il remonte en arrière à l'angle de la descente. Si cet angle dépasse
  celui du flanc du cône de la buse, le brin frotte sur le métal chaud. Les descentes ne
  dépassent donc jamais `angle_buse` : le sommet se décale dans la maille (montée plus raide,
  sans risque : le brin pend sous la buse). Mesurez le flanc de votre buse (≈ 45° sur une buse
  classique) et gardez une marge. Si l'étage est trop haut pour la largeur de maille,
  l'application le signale : baissez la hauteur d'étage ou le nombre de cellules.
- Ventilation forcée à 100 %. Une buse 5 à 10 °C plus froide aide les brins à figer.
- La vitesse de l'axe Z reste sous `vitesse_z_max` (Réglages › Imprimante, préréglée selon
  l'imprimante).
- Seul le **G-code** contient les jours ; la vue 3D montre les brins, le STL reste plein.
- Une seule pièce : la dentelle est ignorée pour les assemblages (gigogne, couvercle…).
- **Commencez par la pièce de calibration** (bouton de l'onglet Dentelle) : cylindre Ø 40 mm,
  12 mailles, étages de 3 mm en bas à 8 mm en haut.

| symptôme | correction |
|---|---|
| anneaux qui glissent vers l'intérieur, étage suivant qui ne touche plus | `pression` ↑ (0,4–0,5), `pause_noeud` ↑ (0,3–0,5 s), `vitesse_anneau` ↓ |
| brins ondulés, en zigzag | `debit_fil` ↓ (0,75), buse plus froide |
| sommets qui retombent sous l'anneau | `affaissement` ↑, `pause` ↑ |
| montées qui ne restent pas droites | `vitesse_montee` ↓, `pause` ↑ |
| cheveux, fils | buse 5 à 10 °C plus froide, `pause` et `pause_noeud` ↓ |
| brin qui touche le flanc chaud de la buse pendant les descentes | `angle_buse` ↓ (35°) |

### Réglages (Imprimante, Filament, Impression)

Comme dans un trancheur, les réglages sont rangés en trois pages :

- **Imprimante** : ce qui ne change pas d'un filament à l'autre (plateau, buse, firmware, macros).
- **Filament** : un profil par filament. Choisissez un profil dans la liste, modifiez-le, puis
  **Enregistrer le profil** : il est rangé dans `sorties/reglages/filaments/` et apparaît dans la
  liste avec une ★. Températures de 1re couche (la macro `PRINT_START` les reçoit, puis les
  températures normales sont envoyées après la 1re couche), couches sans ventilation, débit,
  rétraction (avec seuil de déplacement et z-hop) et prix au kilo (coût estimé à l'export).
- **Impression** : hauteur de 1re couche, hauteur de couche, largeur de ligne, couches de fond,
  vitesses.

### Plaques de test (PETG transparent Arianeplast)

Onglet **Plaques** : une série de plaques **35 × 70 mm** (2 mm d'épaisseur par défaut),
pleines, en lignes parallèles, chacune avec ses propres réglages. Les réglages sont gravés en
**empreinte dans le bas de la plaque** (bande du bord avant) :

- `dessous` (par défaut) : en creux dans les premières couches, côté plateau. Sur du PETG
  transparent on la lit **à travers** la plaque, à l'endroit, vue de dessus ; la face du
  dessus reste lisse pour juger la transparence ;
- `dessus` : en creux dans les dernières couches ; `aucune` : sans texte.

Par défaut, seuls le **numéro** et les **paramètres testés** sont gravés (les autres réglages,
communs à toute la série, sont dans la fiche CSV et l'en-tête du G-code) : moins de texte, donc
une police plus grande. Série de températures, grille température × débit :

```
#3          plaque n° 3               #3
T245        buse 245 °C               T245
                                      D105    débit 105 %
```

Lettres : `T` buse (°C), `D` débit (%), `V` vitesse (mm/s), `F` ventilateur (%), `H` couche
(1/100 mm : H20 = 0,20 mm), `L` largeur de ligne (1/100 mm), `ML` / `MT` / `MX` lignes
longitudinales / transversales / croisées. Pour graver d'autres champs, décochez **texte
automatique** et choisissez-les.

Lisibilité de l'empreinte :

- **police** `auto` : la grande police 5 × 7 si le texte tient dans 40 % de la longueur, sinon la
  petite 3 × 5 ; ou imposez l'une ou l'autre. Le pixel vaut deux largeurs de ligne (0,9 mm) ;
  « pixel du texte » l'agrandit ;
- **contour autour des lettres** : un périmètre longe chaque lettre dans les couches gravées,
  les lignes s'arrêtent contre lui ; les bords sont nets, sans bouts de lignes qui filent dans
  les creux ;
- **lecture côté plateau** : texte en miroir, lisible en retournant la plaque (la face du plateau
  est la plus lisse et ne regarde pas à travers 2 mm de lignes) ; « à travers la plaque » le
  lit vu de dessus ;
- **profondeur** 0,8 mm par défaut (4 couches de 0,20 mm).

1. **Préréglage PETG transparent Arianeplast** : charge ce profil dans **Réglages › Filament**
   (plateau 80 °C à la 1re couche puis 75 °C, z-hop 0,2 mm, rétraction 1 mm) et règle la base des
   plaques : buse 245 °C, débit 1,05, 25 mm/s, ventilateur 20 %, couches 0,20 mm (vérifiez la plage
   indiquée sur votre bobine). Le bandeau de l'onglet rappelle le filament actif et passe au rouge
   s'il ne s'agit pas de PETG. Le filament est le même pour la forme et les plaques, comme dans un
   trancheur ; il est repris au lancement suivant.
2. Choisissez le **paramètre testé** (température, débit, vitesse, ventilateur, hauteur de
   couche, largeur de ligne, orientation des lignes) ; les valeurs se modifient au clavier
   (`235 240 245`, `1,02 ; 1,05`). Un second paramètre donne une grille (toutes les combinaisons).
3. **Exporter G-code + fiche** (en haut de l'onglet, avec le nom des fichiers et le journal) :
   le G-code et une fiche `.csv` (Excel / LibreOffice) pour noter chaque plaque (transparence,
   bulles, lignes visibles, fils, adhérence), dans le dossier `sorties/` (bouton **Ouvrir le
   dossier**). La vue de droite passe aux plaques en ouvrant cet onglet et les garde sur les
   onglets **Impression** et **Export** ; l'onglet Export exporte alors les plaques. Elle revient à
   la forme en ouvrant Forme, Déformations, Emboîtement ou Dentelle.

Les plaques s'impriment **l'une après l'autre** : chacune à sa température (ordre croissant pour
ne jamais attendre le refroidissement), avec une ligne d'amorçage après chaque chauffe, son débit,
sa vitesse, sa ventilation (à partir de la 2e couche) et sa hauteur de couche. Les plaques sont
gravées et posées de l'arrière vers l'avant ; au-delà d'un plateau, un G-code par lot. Si les
plaques sont plus épaisses que le **dégagement de la tête** (hauteur libre sous le conduit de
ventilation), cochez **un G-code par plaque**. Le pixel du texte est un multiple de la largeur de
ligne et ses bords tombent entre deux lignes : l'empreinte retire des lignes entières, nette dans
les deux sens de remplissage. Le **STL** (plaques avec empreinte) sert à trancher ailleurs ; les
réglages de chaque plaque sont alors à saisir à la main.

Pistes pour la transparence : buse chaude (245–255 °C), lent (20–30 mm/s), débit légèrement
élevé (1,03–1,08) pour combler les vides entre lignes, peu ou pas de ventilation, couches
épaisses, lignes toutes dans le même sens, filament bien sec.

En script :

```python
from formes.plaques import *

p = ParametresImpression(**PETG_ARIANEPLAST, plateau=(300.0, 300.0))
cfg = plan(REGLAGE_TRANSPARENT, temp_buse=[240, 250, 260], flux=[1.02, 1.06])  # 6 plaques
exporter_plaques(cfg, "sorties/petg.gcode", p)
exporter_fiche(cfg, "sorties/petg.csv", p)
exporter_stl_plaques(serie("ventilateur", [0, 20, 40]), "sorties/petg_vent.stl", p)
```

### G-code

- `mode="spirale"` : mode vase, Z continu, sans couture (une seule pièce).
- `mode="couches"` : plusieurs pièces par couche avec rétractions ; utilisé automatiquement
  pour les assemblages.
- Fond plein (périmètre + remplissage croisé) sur `couches_fond` couches pour les pièces
  qui en ont un.
- Avertissements : dépassement du plateau ou de la hauteur max, surplombs > 50°.
- `firmware="klipper"` (par défaut) ou `firmware="marlin"`.

### Klipper : Mainsail, Moonraker, exclude object, KAMP

| Fonction | Ce qui est écrit dans le G-code |
|---|---|
| Aperçu Mainsail / Fluidd / KlipperScreen | vignettes PNG 32×32 et 300×300 (`; thumbnail begin … end`) |
| Métadonnées Moonraker | ligne `; generated by generateur-formes <version> on …` + bloc de fin au format PrusaSlicer : durée estimée, filament (mm, g), nombre de couches, hauteur, températures, buse, type/nom/couleur du filament |
| Annuler une pièce (exclude object) | `EXCLUDE_OBJECT_DEFINE NAME= CENTER= POLYGON=` puis `EXCLUDE_OBJECT_START/END` autour de chaque pièce, à chaque couche ; chaque bloc se termine rétracté |
| KAMP / maillage adaptatif | objets définis **avant** `PRINT_START` ; options `maillage_adaptatif=True` (`BED_MESH_CALIBRATE ADAPTIVE=1`) et `purge="LINE_PURGE"` / `"VORON_PURGE"` |
| Progression par couche | `SET_PRINT_STATS_INFO TOTAL_LAYER=` / `CURRENT_LAYER=` |
| Rétraction firmware | `retraction_firmware=True` → `G10` / `G11` |

Format vérifié avec l'analyseur de métadonnées de Moonraker
(`moonraker/components/file_manager/metadata.py`) : slicer, durée, couches, filament,
températures et vignettes sont reconnus.

Configuration Klipper nécessaire (`printer.cfg`) :

```ini
[exclude_object]

[gcode_macro PRINT_START]
gcode:
    {% set BED = params.BED|default(60)|float %}
    {% set EXTRUDER = params.EXTRUDER|default(210)|float %}
    M190 S{BED}
    G28
    M109 S{EXTRUDER}
    # si vous laissez maillage_adaptatif=False / purge=None dans le notebook :
    # BED_MESH_CALIBRATE ADAPTIVE=1
    # LINE_PURGE
```

La macro de démarrage est modifiable (`macro_debut`, avec `{temp_plateau}`, `{temp_buse}` ou
tout autre champ de `ParametresImpression`). `macro_debut=None` génère un démarrage standard
`M190 / M109 / G28`. Ne lancez pas le maillage ou la purge deux fois : si `PRINT_START` s'en
charge déjà, gardez `maillage_adaptatif=False` et `purge=None`.

## Utilisation en script

(voir aussi `generateur_formes_script.ipynb`)

```python
from formes import *

gen = Generateur(
    Base(profil="polygone", cotes=7, rayon=35, hauteur=90),
    [Fuseau(echelle_haut=0.6), Torsion(angle=180), Plis(actif=False)],
    Gigogne(nombre=3),
)
assemblage = gen.generer()
exporter_html(figure_3d(assemblage), "sorties/vase.html")
assemblage.exporter_stl("sorties/vase.stl")   # pièces posées pour l'impression
exporter_gcode(assemblage, "sorties/vase.gcode",
               ParametresImpression(mode="couches", maillage_adaptatif=True, purge="LINE_PURGE"))
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

L'application (`formes/application.py`) génère ses curseurs automatiquement à partir des
`param(...)` : ajoutez le module à la liste `TOUTES` en bas du fichier et il apparaît
dans l'onglet Déformations.

## Tests

```bash
.venv/bin/python -m pip install pytest      # Windows : .venv\Scripts\python …
.venv/bin/python -m pytest tests
```
