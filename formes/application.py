"""Application graphique complète (ipywidgets) : aucune saisie de code.

Tout se règle avec des menus, curseurs, cases et boutons :

- **Forme**        : profil de base et ses dimensions ;
- **Déformations** : chaque module s'active d'une case, se règle aux curseurs
                     et se déplace dans l'ordre d'application (↑ / ↓) ;
- **Emboîtement**  : choix par boutons radio ;
- **Impression**   : préréglages d'imprimante et de filament, firmware, mode,
                     options Klipper (macros, purge, maillage adaptatif…) ;
- **Plaques test** : plaques 35 × 70 mm pour régler un filament (PETG
                     transparent Arianeplast), réglages gravés en empreinte ;
- **Export**       : HTML, STL et G-code en un clic, sauvegarde des réglages.

Lancement dans un notebook ::

    from formes.application import application
    application()

ou, sans aucun code visible : ``python -m voila generateur_formes.ipynb``.
"""

from __future__ import annotations

import html
import json
import os
import random
from dataclasses import asdict, fields, replace
from datetime import datetime
from pathlib import Path

from .bases import PROFILS, Base
from .deformations import TOUTES, Fuseau, Torsion
from .dentelle import Dentelle
from .emboitements import TOUS, Luminaire
from .gcode import ParametresImpression, _porte_a_faux, exporter_gcode
from .generateur import Generateur
from .geometrie import Assemblage
from . import plaques as PL
from .visualisation import figure_3d, figure_trajet, exporter_html

# ---------------------------------------------------------------------------
# Préréglages
# ---------------------------------------------------------------------------

IMPRIMANTES = {
    "Personnalisée": None,
    "Voron 2.4 – 350": dict(plateau=(350.0, 350.0), hauteur_max=340.0, firmware="klipper", vitesse_z_max=15.0),
    "Voron 2.4 – 300": dict(plateau=(300.0, 300.0), hauteur_max=290.0, firmware="klipper", vitesse_z_max=15.0),
    "Voron Trident – 300": dict(plateau=(300.0, 300.0), hauteur_max=250.0, firmware="klipper", vitesse_z_max=15.0),
    "Voron 0.2 – 120": dict(plateau=(120.0, 120.0), hauteur_max=120.0, firmware="klipper", vitesse_z_max=15.0),
    "Creality K1 / K1C": dict(plateau=(220.0, 220.0), hauteur_max=250.0, firmware="klipper", vitesse_z_max=10.0),
    "Sovol SV06 Plus / SV07 (Klipper)": dict(plateau=(300.0, 300.0), hauteur_max=340.0, firmware="klipper", vitesse_z_max=10.0),
    "Ender 3 / Ender 3 V2 (Marlin)": dict(plateau=(220.0, 220.0), hauteur_max=250.0, firmware="marlin", vitesse_z_max=5.0),
    "Ender 3 + Klipper": dict(plateau=(220.0, 220.0), hauteur_max=250.0, firmware="klipper", vitesse_z_max=5.0),
    "Prusa MK3S / MK4 (Marlin)": dict(plateau=(250.0, 210.0), hauteur_max=210.0, firmware="marlin", vitesse_z_max=12.0),
}

# Profils de filament (page Réglages › Filament). Vérifiez les plages sur l'étiquette de la bobine.
FILAMENTS = {
    "PLA": dict(filament_type="PLA", filament_couleur="#E8B04A", densite_g_cm3=1.24, cout_kg=20.0,
                temp_buse=210, temp_buse_premiere_couche=215, temp_plateau=60, temp_plateau_premiere_couche=60,
                ventilateur=255, couches_sans_ventilateur=1, flux=1.0,
                retraction=1.0, vitesse_retraction=35.0, z_hop=0.0),
    "PETG": dict(filament_type="PETG", filament_couleur="#4AA3E8", densite_g_cm3=1.27, cout_kg=22.0,
                 temp_buse=235, temp_buse_premiere_couche=240, temp_plateau=80, temp_plateau_premiere_couche=80,
                 ventilateur=128, couches_sans_ventilateur=3, flux=1.0,
                 retraction=1.0, vitesse_retraction=30.0, z_hop=0.2),
    "PETG transparent Arianeplast": dict(
        filament_type="PETG", filament_couleur="#DDEEF2", densite_g_cm3=1.27, cout_kg=22.0,
        temp_buse=245, temp_buse_premiere_couche=245, temp_plateau=75, temp_plateau_premiere_couche=80,
        ventilateur=51, couches_sans_ventilateur=3, flux=1.05,
        retraction=1.0, vitesse_retraction=30.0, z_hop=0.2),
    "ABS": dict(filament_type="ABS", filament_couleur="#E8574A", densite_g_cm3=1.04, cout_kg=20.0,
                temp_buse=245, temp_buse_premiere_couche=250, temp_plateau=100, temp_plateau_premiere_couche=105,
                ventilateur=0, couches_sans_ventilateur=3, flux=1.0,
                retraction=0.8, vitesse_retraction=35.0, z_hop=0.0),
    "ASA": dict(filament_type="ASA", filament_couleur="#9AA0A6", densite_g_cm3=1.07, cout_kg=25.0,
                temp_buse=250, temp_buse_premiere_couche=255, temp_plateau=100, temp_plateau_premiere_couche=105,
                ventilateur=0, couches_sans_ventilateur=3, flux=1.0,
                retraction=0.8, vitesse_retraction=35.0, z_hop=0.0),
    "TPU": dict(filament_type="TPU", filament_couleur="#5FC28A", densite_g_cm3=1.21, cout_kg=30.0,
                temp_buse=225, temp_buse_premiere_couche=225, temp_plateau=50, temp_plateau_premiere_couche=50,
                ventilateur=128, couches_sans_ventilateur=1, flux=1.0,
                retraction=0.5, vitesse_retraction=20.0, z_hop=0.0),
}

# paramètres qui appartiennent au profil de filament
CHAMPS_FILAMENT = (
    "filament_nom", "filament_type", "filament_couleur", "diametre_filament", "densite_g_cm3", "cout_kg",
    "temp_buse", "temp_buse_premiere_couche", "temp_plateau", "temp_plateau_premiere_couche",
    "ventilateur", "couches_sans_ventilateur", "flux",
    "retraction", "vitesse_retraction", "retraction_min_deplacement", "z_hop",
)

MACROS_DEBUT = {
    "PRINT_START BED=… EXTRUDER=…": "PRINT_START BED={temp_plateau} EXTRUDER={temp_buse}",
    "START_PRINT BED_TEMP=… EXTRUDER_TEMP=…":
        "START_PRINT BED_TEMP={temp_plateau} EXTRUDER_TEMP={temp_buse}",
    "Aucune (M190 / M109 / G28 standard)": None,
}
MACROS_FIN = {"PRINT_END": "PRINT_END", "END_PRINT": "END_PRINT", "Aucune (fin standard)": None}
PURGES = {
    "Ligne générée ici": "interne",
    "KAMP : LINE_PURGE": "LINE_PURGE",
    "KAMP : VORON_PURGE": "VORON_PURGE",
    "Aucune (PRINT_START s'en charge)": None,
}

# paramètres de la base utiles pour chaque profil (les autres sont masqués)
PARAMS_PROFIL = {
    "cercle": (), "goutte": (),
    "polygone": ("cotes", "arrondi"),
    "etoile": ("cotes", "creux"),
    "superellipse": ("exposant",),
    "fleur": ("cotes", "creux"),
    "engrenage": ("cotes", "creux"),
}
PARAMS_BASE_PROFIL = {"cotes", "creux", "arrondi", "exposant"}

DESCRIPTIONS = {
    "Torsion": "rotation progressive des couches",
    "Fuseau": "évasement, rétrécissement, galbe",
    "Ondulation": "vagues radiales hélicoïdales",
    "Plis": "plissé à arêtes vives",
    "Bruit": "relief organique aléatoire",
    "Courbure": "inclinaison, arc, serpentin",
    "Pincement": "aplatissement elliptique qui tourne",
    "Nervures": "côtes droites ou hélicoïdales",
    "Losanges": "pointes de diamant",
    "Ecailles": "écailles en quinconce",
    "Facettes": "style low poly",
    "Bec": "bec verseur",
    "Gigogne": "coques imbriquées, imprimées en place",
    "Empilement": "modules empilables à col",
    "Reseau": "copies en grille",
    "Couvercle": "couvercle à col ajusté",
    "Luminaire": "abat-jour, fond percé pour douille E27 / E14 / GU10",
}

LIBELLES = {"a poser": "à poser", "alveoles": "alvéoles"}

PL_FILAMENT = "PETG transparent Arianeplast"   # profil du préréglage des plaques
ONGLET_PLAQUES = 5        # position de l'onglet « Plaques test »
ONGLETS_FORME = (0, 1, 2, 3)  # Forme, Déformations, Emboîtement, Dentelle

APERCU = {"Rapide": (60, 144), "Normal": (120, 240), "Fin": (None, None)}

STYLE = {"description_width": "150px"}
LARGEUR = "460px"


def _curseur(nom, valeur, meta, description=None):
    """Curseur adapté au type de la valeur et aux bornes de ``param(...)``."""
    import ipywidgets as W

    commun = dict(description=description or nom.replace("_", " "), style=STYLE,
                  layout=W.Layout(width="98%", max_width=LARGEUR), continuous_update=False)
    if meta.get("choix"):
        options = [(LIBELLES.get(c, c), c) for c in meta["choix"]]
        if len(options) <= 4:          # boutons côte à côte
            w = W.ToggleButtons(options=options, value=valeur, description=commun["description"],
                                style={**STYLE, "button_width": "92px"},
                                layout=W.Layout(flex="0 0 auto", min_height="36px"))
        else:
            w = W.Dropdown(options=options, value=valeur, description=commun["description"],
                           style=STYLE, layout=commun["layout"])
    elif isinstance(valeur, bool):
        w = W.Checkbox(value=valeur, description=commun["description"], indent=False)
    elif isinstance(valeur, int):
        w = W.IntSlider(value=valeur, min=meta.get("min") or 0, max=meta.get("max") or 100,
                        step=int(meta.get("pas") or 1), **commun)
    else:
        pas = meta.get("pas") or 0.1
        decimales = max(0, -int(f"{pas:e}".split("e")[1]))
        w = W.FloatSlider(value=valeur, min=meta.get("min") or 0.0, max=meta.get("max") or 100.0,
                          step=pas, readout_format=f".{decimales}f", **commun)
    if meta.get("aide"):
        w.tooltip = meta["aide"]
    return w


class Application:
    """État de l'application + widgets. ``Application().afficher()`` l'affiche."""

    def __init__(self, dossier="sorties"):
        import ipywidgets as W

        self.W = W
        self.dossier = Path(dossier)
        self.dossier_reglages = self.dossier / "reglages"
        self._suspendu = False
        self._derniere_figure = None
        self.mode_vue = "forme"            # "forme" | "plaques" : ce que montre la vue et exporte Export

        # -- état ---------------------------------------------------------------
        self.base = Base(profil="polygone", cotes=7, rayon=35, hauteur=90, couches=150, points=360)
        self.deformations = [cls(actif=False) for cls in TOUTES]
        for d in self.deformations:
            if isinstance(d, Fuseau):
                d.actif, d.echelle_haut, d.ventre = True, 0.75, 0.3
            if isinstance(d, Torsion):
                d.actif, d.angle = True, 120.0
        self.emboitements = {cls.__name__: cls() for cls in TOUS}
        self.emboitement_choisi = "Aucun"
        self.dentelle = Dentelle(actif=False)
        self.impression = ParametresImpression(filament_nom="PLA", **FILAMENTS["PLA"])
        self.impression.hauteur_premiere_couche = self.impression.hauteur_couche
        memorise = self._filament_memorise()        # filament de la dernière session
        for attr, v in (memorise or {}).items():
            setattr(self.impression, attr, v)
        self.plaque_base = PL.ReglagePlaque()
        self.plaques = PL.Plaques()
        self.widgets: dict[tuple[str, str], W.Widget] = {}

        # -- construction ---------------------------------------------------------
        self.sortie = W.Output(layout=W.Layout(width="100%"))
        self.infos = W.HTML()
        self.journal = W.Output(layout=W.Layout(width=LARGEUR, max_height="260px", overflow="auto"))

        onglets = W.Tab(children=[self._onglet_forme(), self._onglet_deformations(),
                                  self._onglet_emboitement(), self._onglet_dentelle(),
                                  self._onglet_reglages(), self._onglet_plaques(),
                                  self._onglet_export()])
        self.onglets = onglets
        for i, t in enumerate(["Forme", "Déformations", "Emboîtement", "Dentelle", "Réglages",
                               "Plaques", "Export"]):
            onglets.set_title(i, t)
        onglets.layout = W.Layout(width="590px")
        # la vue suit l'onglet : plaques de test sur « Plaques test », forme sur les onglets de
        # forme ; Impression et Export gardent ce qui était affiché (et l'exportent)
        onglets.observe(self._changer_onglet, names="selected_index")

        self.qualite = W.ToggleButtons(options=list(APERCU), value="Rapide",
                                       description="Aperçu", style={"button_width": "70px"},
                                       tooltips=["calcul allégé", "intermédiaire", "résolution d'export"])
        self.qualite.observe(lambda _: self.rafraichir(), names="value")
        hasard = W.Button(description="Surprise", icon="random", tooltip="forme aléatoire",
                          layout=W.Layout(width="110px"))
        hasard.on_click(lambda _: self.surprise())
        barre = W.HBox([self.qualite, hasard])

        self.vue = W.VBox([
            W.HTML("<h2 style='margin:4px 0'>Générateur de formes</h2>"),
            W.HBox([W.VBox([barre, onglets], layout=W.Layout(flex="0 0 600px", width="600px")),
                    W.VBox([self.infos, self.sortie],
                           layout=W.Layout(flex="1 1 0%", min_width="0", overflow="hidden"))],
                   layout=W.Layout(width="100%", align_items="flex-start")),
        ])
        self._maj_visibilite_base()
        self._maj_visibilite_klipper()
        self.rafraichir()

    # ------------------------------------------------------------------ outils
    def _lier(self, objet, nom, widget, cle, apres=None):
        """Relie un widget à un attribut ; tout changement régénère l'aperçu."""
        self.widgets[(cle, nom)] = widget

        def changer(ch):
            setattr(objet, nom, ch["new"])
            if apres:
                apres()
            if not self._suspendu:
                self.rafraichir()

        widget.observe(changer, names="value")
        return widget

    def _titre(self, texte):
        return self.W.HTML(f"<b style='font-size:13px'>{texte}</b>")

    # ------------------------------------------------------------------ onglets
    def _onglet_forme(self):
        W = self.W
        profil = W.Dropdown(options=PROFILS, value=self.base.profil, description="profil",
                            style=STYLE, layout=W.Layout(width=LARGEUR))
        self._lier(self.base, "profil", profil, "Base", apres=self._maj_visibilite_base)
        enfants = [profil]
        for n, v, m in self.base.parametres():
            if n == "profil":
                continue
            desc = {"couches": "résolution verticale", "points": "points par contour"}.get(n)
            enfants.append(self._lier(self.base, n, _curseur(n, v, m, desc), "Base"))
        aide = W.HTML("<small>« Aperçu » (en haut) allège le calcul pendant les réglages ; "
                      "les exports utilisent toujours la résolution réglée ici.</small>")
        return W.VBox(enfants + [aide])

    def _maj_visibilite_base(self):
        utiles = set(PARAMS_PROFIL.get(self.base.profil, ()))
        for n in PARAMS_BASE_PROFIL:
            w = self.widgets.get(("Base", n))
            if w is not None:
                w.layout.display = "" if n in utiles else "none"

    def _onglet_deformations(self):
        W = self.W
        self.acc_deformations = W.Accordion()
        self.blocs_deformations = {}
        for d in self.deformations:
            case = W.Checkbox(value=d.actif, description="actif", indent=False)
            self.widgets[(d.nom, "actif")] = case
            curseurs = [self._lier(d, n, _curseur(n, v, m), d.nom) for n, v, m in d.parametres()]
            corps = W.VBox(curseurs, layout=W.Layout(display="" if d.actif else "none"))
            haut = W.Button(icon="arrow-up", tooltip="appliquer plus tôt", layout=W.Layout(width="40px"))
            bas = W.Button(icon="arrow-down", tooltip="appliquer plus tard", layout=W.Layout(width="40px"))
            haut.on_click(lambda _, d=d: self._deplacer(d, -1))
            bas.on_click(lambda _, d=d: self._deplacer(d, +1))

            def basculer(ch, d=d, corps=corps):
                d.actif = ch["new"]
                corps.layout.display = "" if ch["new"] else "none"
                self._maj_titres()
                if not self._suspendu:
                    self.rafraichir()

            case.observe(basculer, names="value")
            entete = W.HBox([case, haut, bas,
                             W.HTML(f"<i style='color:gray'>{DESCRIPTIONS.get(d.nom, '')}</i>")])
            self.blocs_deformations[d.nom] = W.VBox([entete, corps])
        tout_couper = W.Button(description="Tout désactiver", icon="power-off",
                               layout=W.Layout(width="150px"))
        tout_couper.on_click(lambda _: self._tout_desactiver())
        self._ordonner_accordeon()
        aide = W.HTML("<small>Les modules cochés s'appliquent de haut en bas ; "
                      "↑ / ↓ changent l'ordre.</small>")
        return W.VBox([W.HBox([tout_couper, aide]), self.acc_deformations])

    def _ordonner_accordeon(self):
        self.acc_deformations.children = [self.blocs_deformations[d.nom] for d in self.deformations]
        self._maj_titres()

    def _maj_titres(self):
        rang = 0
        for i, d in enumerate(self.deformations):
            if d.actif:
                rang += 1
                titre = f"✔ {rang}. {d.nom}"
            else:
                titre = f"    {d.nom}"
            self.acc_deformations.set_title(i, titre)

    def _deplacer(self, d, sens):
        i = self.deformations.index(d)
        j = i + sens
        if 0 <= j < len(self.deformations):
            ouvert = self.acc_deformations.selected_index
            self.deformations[i], self.deformations[j] = self.deformations[j], self.deformations[i]
            self._ordonner_accordeon()
            if ouvert == i:
                self.acc_deformations.selected_index = j
            if d.actif:
                self.rafraichir()

    def _tout_desactiver(self):
        self._suspendu = True
        for d in self.deformations:
            self.widgets[(d.nom, "actif")].value = False
        self._suspendu = False
        self.rafraichir()

    def _onglet_emboitement(self):
        W = self.W
        options = ["Aucun"] + list(self.emboitements)
        libelles = [("Aucun : une seule pièce", "Aucun")] + \
                   [(f"{n} : {DESCRIPTIONS.get(n, '')}", n) for n in self.emboitements]
        radio = W.RadioButtons(options=libelles, value="Aucun", layout=W.Layout(width=LARGEUR))
        self.widgets[("Emboitement", "choix")] = radio
        panneaux = {}
        for nom, e in self.emboitements.items():
            panneaux[nom] = W.VBox([self._lier(e, n, _curseur(n, v, m), nom)
                                    for n, v, m in e.parametres()],
                                   layout=W.Layout(display="none"))

        def choisir(ch):
            self.emboitement_choisi = ch["new"]
            for n, p in panneaux.items():
                p.layout.display = "" if n == ch["new"] else "none"
            if not self._suspendu:
                self.rafraichir()

        radio.observe(choisir, names="value")
        assert set(options[1:]) == set(panneaux)
        return W.VBox([radio, *panneaux.values()])

    def _onglet_dentelle(self):
        W = self.W
        d = self.dentelle
        case = W.Checkbox(value=d.actif, description="paroi en dentelle (impression non planaire)",
                          indent=False)
        self.widgets[("Dentelle", "actif")] = case
        corps = W.VBox([self._lier(d, n, _curseur(n, v, m), "Dentelle") for n, v, m in d.parametres()],
                       layout=W.Layout(display="" if d.actif else "none"))

        def basculer(ch):
            d.actif = ch["new"]
            corps.layout.display = "" if ch["new"] else "none"
            if not self._suspendu:
                self.rafraichir()

        case.observe(basculer, names="value")
        calibration = W.Button(description="Pièce de calibration", icon="flask",
                               tooltip="petit cylindre, étages de 3 à 8 mm du bas vers le haut",
                               layout=W.Layout(width="220px"))
        calibration.on_click(lambda _: self._executer(self.calibration_dentelle))
        aide = W.HTML(
            "<small>Impression en fil : à chaque étage, la buse monte lentement dans le vide, "
            "marque une pause pour que le brin fige, redescend en diagonale, puis imprime un "
            "anneau qui relie les sommets et sert d'appui à l'étage suivant. Seul le <b>G-code</b> "
            "contient les jours (le STL reste plein). Ventilation à 100 %, buse 5 à 10 °C plus "
            "froide que d'habitude. Commencez par la <b>pièce de calibration</b>.</small>")
        return W.VBox([case, corps, calibration, aide])

    def calibration_dentelle(self):
        """Petit cylindre de test : étages de 3 mm (bas) à 8 mm (haut)."""
        self._suspendu = True
        try:
            regles = {("Base", "profil"): "cercle", ("Base", "rayon"): 20.0, ("Base", "hauteur"): 40.0,
                      ("Dentelle", "motif"): "losanges", ("Dentelle", "cellules"): 12,
                      ("Dentelle", "hauteur_maille"): 3.0, ("Dentelle", "maille_haut"): 8.0,
                      ("Dentelle", "bord_bas"): 3.0, ("Dentelle", "bord_haut"): 3.0,
                      ("Dentelle", "actif"): True, ("Emboitement", "choix"): "Aucun"}
            for d in self.deformations:
                regles[(d.nom, "actif")] = False
            for cle, v in regles.items():
                self.widgets[cle].value = v
            self.nom.value = f"calibration-dentelle-{datetime.now():%H%M%S}"
        finally:
            self._suspendu = False
        self.rafraichir()
        print("🧪 pièce de calibration chargée : imprimez-la, puis gardez l'étage le plus haut "
              "dont les brins sont restés droits et soudés à l'anneau")

    def _onglet_reglages(self):
        """Réglages façon trancheur : trois pages Imprimante, Filament, Impression."""
        W = self.W
        p = self.impression
        lay = W.Layout(width=LARGEUR)

        def menu(cle, options, valeur, description, attr=None, apres=None):
            if isinstance(options, dict):
                options = list(options.items())             # (libellé, valeur)
            w = W.Dropdown(options=options, value=valeur, description=description, style=STYLE, layout=lay)
            if attr:
                return self._lier(p, attr, w, "Impression", apres=apres)
            self.widgets[("Impression", cle)] = w
            return w

        def curseur(attr, mini, maxi, pas, description, aide=""):
            return self._lier(p, attr, _curseur(attr, getattr(p, attr),
                                                {"min": mini, "max": maxi, "pas": pas, "aide": aide},
                                                description), "Impression")

        def bascule(attr, options, description, apres=None):
            w = W.ToggleButtons(options=options, value=getattr(p, attr), description=description,
                                style={**STYLE, "button_width": "120px"},
                                layout=W.Layout(flex="0 0 auto", min_height="36px"))
            return self._lier(p, attr, w, "Impression", apres=apres)

        def case(attr, description):
            return self._lier(p, attr, W.Checkbox(value=getattr(p, attr), description=description,
                                                  indent=False), "Impression")

        def page(*enfants):
            return _defilant(W.VBox(list(enfants), layout=W.Layout(max_height="680px", overflow="auto")))

        # ------------------------------------------------------------ Imprimante
        imprimante = menu("imprimante", list(IMPRIMANTES), "Personnalisée", "imprimante")
        plateau_x = W.IntSlider(value=int(p.plateau[0]), min=80, max=500, step=5, description="plateau X (mm)",
                                style=STYLE, layout=lay, continuous_update=False)
        plateau_y = W.IntSlider(value=int(p.plateau[1]), min=80, max=500, step=5, description="plateau Y (mm)",
                                style=STYLE, layout=lay, continuous_update=False)
        self.widgets[("Impression", "plateau_x")] = plateau_x
        self.widgets[("Impression", "plateau_y")] = plateau_y

        def changer_plateau(_):
            p.plateau = (float(plateau_x.value), float(plateau_y.value))
            if not self._suspendu:
                self.rafraichir()

        plateau_x.observe(changer_plateau, names="value")
        plateau_y.observe(changer_plateau, names="value")
        imprimante.observe(lambda ch: IMPRIMANTES[ch["new"]] and self._appliquer(IMPRIMANTES[ch["new"]]),
                           names="value")
        buse = W.Dropdown(options=[0.2, 0.25, 0.4, 0.5, 0.6, 0.8, 1.0], value=p.diametre_buse,
                          description="buse (mm)", style=STYLE, layout=lay)
        self._lier(p, "diametre_buse", buse, "Impression",
                   apres=lambda: setattr(self.widgets[("Impression", "largeur_ligne")], "value",
                                         round(1.125 * p.diametre_buse, 2)))
        macro_debut = menu("macro_debut", MACROS_DEBUT, p.macro_debut, "macro de début", attr="macro_debut")
        macro_fin = menu("macro_fin", MACROS_FIN, p.macro_fin, "macro de fin", attr="macro_fin")
        purge = menu("purge", PURGES, p.purge, "purge", attr="purge")
        self.bloc_klipper = W.VBox([
            self._titre("Klipper"),
            macro_debut, macro_fin, purge,
            case("maillage_adaptatif", "maillage adaptatif (BED_MESH_CALIBRATE ADAPTIVE=1)"),
            case("exclude_object", "exclude object (annuler une pièce depuis Mainsail)"),
            case("retraction_firmware", "rétraction firmware (G10 / G11)"),
            W.HTML("<small>Si PRINT_START fait déjà le maillage et la purge : décochez le maillage "
                   "et choisissez « Aucune » pour la purge. La macro reçoit les températures de la "
                   "1re couche.</small>"),
        ])
        vignettes = W.Checkbox(value=bool(p.vignettes), description="vignettes d'aperçu (Mainsail)",
                               indent=False)
        self.widgets[("Impression", "vignettes_actives")] = vignettes
        vignettes.observe(lambda ch: setattr(p, "vignettes", ((32, 32), (300, 300)) if ch["new"] else ()),
                          names="value")
        page_imprimante = page(
            imprimante,
            bascule("firmware", ["klipper", "marlin"], "firmware", apres=self._maj_visibilite_klipper),
            self._titre("Volume d'impression"),
            plateau_x, plateau_y,
            curseur("hauteur_max", 50, 600, 5, "hauteur max (mm)"),
            self._titre("Extrudeur et axes"),
            buse,
            curseur("vitesse_z_max", 2, 40, 1, "vitesse Z max (mm/s)",
                    "limite de l'axe Z (max_z_velocity de Klipper), utilisée par la dentelle et le z-hop"),
            vignettes,
            self.bloc_klipper,
        )

        # ------------------------------------------------------------ Filament
        profils = self._liste_filaments()
        self.choix_filament = W.Dropdown(options=profils, value=p.filament_nom
                                         if p.filament_nom in [n for _, n in profils] else None,
                                         description="profil", style=STYLE, layout=lay)
        self.choix_filament.observe(lambda ch: ch["new"] and self.charger_filament(ch["new"]), names="value")
        enregistrer = W.Button(description="Enregistrer le profil", icon="save", layout=W.Layout(width="200px"),
                               tooltip="sous le nom ci-dessous, dans sorties/reglages/filaments")
        enregistrer.on_click(lambda _: self._executer(self.enregistrer_filament, self.journal_filament))
        self.journal_filament = W.Output(layout=W.Layout(width=LARGEUR))
        nom = W.Text(value=p.filament_nom, description="nom", style=STYLE, layout=lay, continuous_update=False)
        self._lier(p, "filament_nom", nom, "Impression")
        types = ["PLA", "PETG", "ABS", "ASA", "TPU", "PC", "PA", "HIPS", "PVA", "autre"]
        type_ = W.Dropdown(options=types if p.filament_type in types else types + [p.filament_type],
                           value=p.filament_type, description="type", style=STYLE, layout=lay)
        self._lier(p, "filament_type", type_, "Impression")
        couleur = W.ColorPicker(value=p.filament_couleur, description="couleur (Mainsail)",
                                style=STYLE, layout=lay)
        self._lier(p, "filament_couleur", couleur, "Impression")
        vent = W.IntSlider(value=round(p.ventilateur / 2.55), min=0, max=100, step=5,
                           description="ventilateur (%)", style=STYLE, layout=lay, continuous_update=False)
        self.widgets[("Impression", "ventilateur_pct")] = vent
        vent.observe(lambda ch: setattr(p, "ventilateur", round(ch["new"] * 2.55)), names="value")
        page_filament = page(
            W.HBox([self.choix_filament]), enregistrer, self.journal_filament,
            self._titre("Filament"),
            nom, type_, couleur,
            self._lier(p, "diametre_filament",
                       W.Dropdown(options=[1.75, 2.85], value=p.diametre_filament, description="Ø filament (mm)",
                                  style=STYLE, layout=lay), "Impression"),
            curseur("densite_g_cm3", 0.9, 2.0, 0.01, "densité (g/cm³)"),
            curseur("cout_kg", 0, 100, 1, "prix (€/kg)"),
            self._titre("Températures"),
            curseur("temp_buse_premiere_couche", 150, 320, 1, "buse 1re couche (°C)"),
            curseur("temp_buse", 150, 320, 1, "buse (°C)"),
            curseur("temp_plateau_premiere_couche", 0, 130, 1, "plateau 1re couche (°C)"),
            curseur("temp_plateau", 0, 130, 1, "plateau (°C)"),
            self._titre("Refroidissement"),
            vent,
            curseur("couches_sans_ventilateur", 0, 10, 1, "couches sans ventil.",
                    "le ventilateur démarre après ce nombre de couches"),
            self._titre("Débit et rétraction"),
            curseur("flux", 0.8, 1.2, 0.01, "multiplicateur de débit"),
            curseur("retraction", 0, 8, 0.1, "rétraction (mm)"),
            curseur("vitesse_retraction", 5, 80, 1, "vitesse rétraction (mm/s)"),
            curseur("retraction_min_deplacement", 0, 10, 0.5, "rétracter au-delà de (mm)",
                    "pas de rétraction pour les déplacements plus courts"),
            curseur("z_hop", 0, 2, 0.05, "levée en déplacement (mm)", "z-hop pendant les déplacements rétractés"),
            W.HTML("<small>Le profil en cours est repris au prochain lancement. Les profils "
                   "enregistrés apparaissent dans la liste (★).</small>"),
        )

        # ------------------------------------------------------------ Impression
        page_impression = page(
            self._titre("Mode"),
            bascule("mode", ["spirale", "couches"], "mode"),
            W.HTML("<small>spirale = mode vase (une pièce, sans couture) ; plusieurs pièces → couches "
                   "automatiquement.</small>"),
            self._titre("Couches et lignes"),
            curseur("hauteur_premiere_couche", 0.08, 0.6, 0.02, "hauteur 1re couche (mm)"),
            curseur("hauteur_couche", 0.08, 0.6, 0.02, "hauteur de couche (mm)"),
            curseur("largeur_ligne", 0.2, 1.4, 0.01, "largeur de ligne (mm)"),
            curseur("couches_fond", 0, 15, 1, "couches de fond"),
            self._titre("Vitesses (mm/s)"),
            curseur("vitesse_premiere_couche", 5, 60, 1, "1re couche"),
            curseur("vitesse", 5, 150, 1, "parois"),
            curseur("vitesse_remplissage", 5, 200, 1, "fond / remplissage"),
            curseur("vitesse_deplacement", 30, 500, 10, "déplacements"),
            self._titre("Contrôles"),
            curseur("angle_max_porte_a_faux", 30, 80, 1, "surplomb max (°)",
                    "au-delà, une alerte s'affiche"),
        )

        # le filament en cours est repris au prochain lancement
        for attr in CHAMPS_FILAMENT:
            w = self.widgets.get(("Impression", attr))
            if w is not None:
                w.observe(lambda _: self._suspendu or self._memoriser_filament(), names="value")
        vent.observe(lambda _: self._suspendu or self._memoriser_filament(), names="value")

        sous = W.Tab(children=[page_imprimante, page_filament, page_impression])
        for i, t in enumerate(["Imprimante", "Filament", "Impression"]):
            sous.set_title(i, t)
        sous.selected_index = 1
        self.sous_onglets_reglages = sous
        return sous

    # ------------------------------------------------------------------ profils
    def _appliquer(self, valeurs: dict):
        """Règle des paramètres d'impression en passant par leurs widgets (aperçu rafraîchi une fois)."""
        p = self.impression
        self._suspendu = True
        try:
            for attr, v in valeurs.items():
                if attr == "plateau":
                    self.widgets[("Impression", "plateau_x")].value = int(v[0])
                    self.widgets[("Impression", "plateau_y")].value = int(v[1])
                    p.plateau = (float(v[0]), float(v[1]))
                    continue
                if attr == "ventilateur" and ("Impression", "ventilateur_pct") in self.widgets:
                    self.widgets[("Impression", "ventilateur_pct")].value = round(v / 2.55)
                w = self.widgets.get(("Impression", attr))
                if w is not None and v is not None:
                    if isinstance(w, self.W.Dropdown) and v not in [o[1] if isinstance(o, tuple) else o
                                                                    for o in w.options]:
                        w.options = list(w.options) + [v]
                    w.value = v
                setattr(p, attr, v)
        finally:
            self._suspendu = False
        self._maj_plaques()
        self.rafraichir()

    def _dossier_filaments(self) -> Path:
        return self.dossier_reglages / "filaments"

    def _liste_filaments(self) -> list:
        """(libellé, nom) : profils intégrés puis profils enregistrés (★)."""
        options = [(n, n) for n in FILAMENTS]
        if self._dossier_filaments().exists():
            for c in sorted(self._dossier_filaments().glob("*.json")):
                try:
                    nom = json.loads(c.read_text(encoding="utf-8"))["filament_nom"]
                except (OSError, ValueError, KeyError):
                    continue
                options.append((f"★ {nom}", nom))
        return options

    def profil_filament(self, nom: str) -> dict:
        """Valeurs d'un profil (enregistré en priorité, sinon intégré)."""
        for c in (self._dossier_filaments().glob("*.json") if self._dossier_filaments().exists() else []):
            try:
                valeurs = json.loads(c.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if valeurs.get("filament_nom") == nom:
                return {k: v for k, v in valeurs.items() if k in CHAMPS_FILAMENT}
        if nom in FILAMENTS:
            return {"filament_nom": nom, **FILAMENTS[nom]}
        raise KeyError(f"profil de filament inconnu : {nom}")

    def charger_filament(self, nom: str):
        self._appliquer(self.profil_filament(nom))
        self._memoriser_filament()
        if hasattr(self, "journal_filament"):
            self.journal_filament.clear_output()
            with self.journal_filament:
                p = self.impression
                print(f"✔ {nom} : buse {p.temp_buse} °C, plateau {p.temp_plateau} °C")

    def filament_actuel(self) -> dict:
        return {k: getattr(self.impression, k) for k in CHAMPS_FILAMENT}

    def enregistrer_filament(self):
        valeurs = self.filament_actuel()
        dossier = self._dossier_filaments()
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = "".join(c if c.isalnum() or c in "-_" else "_" for c in valeurs["filament_nom"]) or "filament"
        chemin = dossier / f"{fichier}.json"
        chemin.write_text(json.dumps(valeurs, ensure_ascii=False, indent=1), encoding="utf-8")
        self.choix_filament.options = self._liste_filaments()
        self._memoriser_filament()
        print("✔ profil enregistré :", chemin)

    def _memoriser_filament(self):
        """Filament repris au prochain lancement."""
        try:
            self.dossier_reglages.mkdir(parents=True, exist_ok=True)
            (self.dossier_reglages / "filament_actif.json").write_text(
                json.dumps(self.filament_actuel(), ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def _filament_memorise(self) -> dict | None:
        try:
            valeurs = json.loads((self.dossier_reglages / "filament_actif.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return {k: v for k, v in valeurs.items() if k in CHAMPS_FILAMENT}

    def _onglet_plaques(self):
        W = self.W
        b, cfg = self.plaque_base, self.plaques
        lay = W.Layout(width="98%", max_width=LARGEUR)

        def curseur(objet, attr, mini, maxi, pas, description, aide=""):
            return self._lier(objet, attr, _curseur(attr, getattr(objet, attr),
                                                    {"min": mini, "max": maxi, "pas": pas, "aide": aide},
                                                    description), "Plaques")

        self.plaques_infos = W.HTML()
        filament = W.Button(description="Préréglage PETG transparent Arianeplast", icon="tint",
                            layout=W.Layout(width="320px"),
                            tooltip="plateau 75 °C, réglages de base favorables à la transparence")
        filament.on_click(lambda _: self._executer(self.preset_petg_transparent, self.journal_plaques))
        self.nom_plaques = W.Text(value=self._nom_plaques_auto(), description="nom des fichiers",
                                  style=STYLE, layout=lay)
        self.journal_plaques = W.Output(layout=W.Layout(width=LARGEUR, max_height="220px", overflow="auto",
                                                        border="1px solid #555", padding="2px 6px"))

        options_serie = [("aucune", "")] + [(k, k) for k in PL.SERIES]
        self.series = []
        lignes_series = []
        for i in range(2):
            menu = W.Dropdown(options=options_serie, value="Température buse" if i == 0 else "",
                              description=f"paramètre testé {i + 1}" if i == 0 else "× paramètre 2",
                              style=STYLE, layout=lay)
            valeurs = W.Text(value="", description="valeurs", style=STYLE, layout=lay,
                             placeholder="ex. 235 240 245 (espaces ou ;)", continuous_update=False)

            def choisir(ch, valeurs=valeurs):
                if ch["new"]:
                    valeurs.value = " ".join(f"{v:g}" if isinstance(v, float) else str(v)
                                             for v in PL.SERIES[ch["new"]][1])
                else:
                    valeurs.value = ""
                self.rafraichir()

            menu.observe(choisir, names="value")
            valeurs.observe(lambda _: self.rafraichir(), names="value")
            self.series.append((menu, valeurs))
            lignes_series += [menu, valeurs]
        self.series[0][1].value = " ".join(str(v) for v in PL.SERIES["Température buse"][1])

        motif = W.ToggleButtons(options=[("longitudinales", "longitudinal"), ("transversales", "transversal"),
                                         ("croisées", "croise")], value=b.motif, description="lignes",
                                style={**STYLE, "button_width": "100px"},
                                layout=W.Layout(flex="0 0 auto", min_height="36px"))
        self._lier(b, "motif", motif, "Plaques")
        vent = curseur(b, "ventilateur", 0, 100, 5, "ventilateur (%)")
        face = W.ToggleButtons(options=[("dessous", "dessous"), ("dessus", "dessus"), ("aucune", "aucune")],
                               value=cfg.face, description="empreinte",
                               style={**STYLE, "button_width": "90px"},
                               layout=W.Layout(flex="0 0 auto", min_height="36px"))
        self._lier(cfg, "face", face, "Plaques")
        champs = W.SelectMultiple(options=[("numéro", "numero"), ("T buse", "temp_buse"), ("D débit", "flux"),
                                           ("V vitesse", "vitesse"), ("F ventilateur", "ventilateur"),
                                           ("H couche", "hauteur_couche"), ("L largeur", "largeur_ligne"),
                                           ("M lignes", "motif")],
                                  value=list(cfg.champs), description="texte gravé", rows=8,
                                  style=STYLE, layout=lay)
        champs.observe(lambda ch: (setattr(cfg, "champs", tuple(ch["new"])), self.rafraichir()),
                       names="value")
        self.widgets[("Plaques", "champs")] = champs

        def case(objet, attr, description):
            return self._lier(objet, attr, W.Checkbox(value=getattr(objet, attr), description=description,
                                                      indent=False), "Plaques")

        self.plaque_seule = W.Checkbox(value=False, description="un G-code par plaque", indent=False)

        def bouton(texte, icone, action, style="", attente=""):
            bt = W.Button(description=texte, icon=icone, button_style=style, layout=W.Layout(width="220px"))

            def clic(_):
                self.journal_plaques.clear_output()
                if attente:
                    with self.journal_plaques:
                        print(f"⏳ {attente}…")
                bt.disabled = True
                try:
                    self._executer(action, self.journal_plaques)
                finally:
                    bt.disabled = False

            bt.on_click(clic)
            return bt

        aide = W.HTML(
            "<small>Les plaques s'impriment <b>l'une après l'autre</b>, chacune à sa température "
            "(ordre croissant), son débit, sa vitesse, sa ventilation et sa hauteur de couche. "
            "L'empreinte <b>dessous</b> se lit à travers le PETG transparent, la face du dessus "
            "reste lisse pour juger la clarté. Machine, plateau, macros et rétraction : onglet "
            "<b>Impression</b>. La fiche CSV sert à noter chaque plaque.<br>"
            "Transparence : buse chaude (245–255 °C), lent (20–30 mm/s), débit 1,03–1,08, "
            "peu de ventilation, couches épaisses, lignes dans un seul sens.</small>")
        self._maj_plaques()
        return _defilant(W.VBox([
            filament,
            self.plaques_infos,
            self._titre("Fichiers"),
            self.nom_plaques,
            W.HBox([bouton("Exporter G-code + fiche", "print", self.exporter_plaques, "success",
                           "export du G-code (quelques secondes)"),
                    bouton("STL (autre trancheur)", "cube", self.exporter_stl_plaques, "", "export du STL")]),
            W.HBox([bouton("Voir le trajet G-code", "road", self.voir_trajet_plaques, "", "calcul du trajet"),
                    bouton("Ouvrir le dossier", "folder-open", self.ouvrir_dossier)]),
            self.journal_plaques,
            self._titre("Série à tester"),
            *lignes_series,
            self._titre("Réglages de base (paramètres non testés)"),
            curseur(b, "temp_buse", 200, 280, 1, "buse (°C)"),
            curseur(b, "flux", 0.8, 1.3, 0.01, "débit"),
            curseur(b, "vitesse", 5, 120, 1, "vitesse (mm/s)"),
            vent,
            curseur(b, "hauteur_couche", 0.08, 0.4, 0.02, "hauteur de couche (mm)"),
            curseur(b, "largeur_ligne", 0.3, 0.9, 0.01, "largeur de ligne (mm)"),
            motif,
            self._titre("Plaque"),
            curseur(cfg, "largeur", 20, 80, 1, "largeur X (mm)"),
            curseur(cfg, "longueur", 30, 150, 1, "longueur Y (mm)"),
            curseur(cfg, "epaisseur", 0.6, 6, 0.2, "épaisseur (mm)"),
            curseur(cfg, "perimetres", 0, 4, 1, "périmètres"),
            face,
            curseur(cfg, "profondeur", 0.2, 2, 0.1, "profondeur (mm)"),
            curseur(cfg, "taille_pixel", 0.6, 2, 0.05, "pixel du texte (mm)",
                    "arrondi à un multiple de la largeur de ligne (2 lignes minimum)"),
            champs,
            self._titre("Plateau"),
            curseur(cfg, "ecart", 2, 30, 1, "écart (mm)"),
            curseur(cfg, "degagement_tete", 1, 20, 0.5, "dégagement tête (mm)",
                    "hauteur libre sous la tête autour de la buse (conduit de ventilation)"),
            case(cfg, "trier_temperature", "imprimer par température croissante"),
            case(cfg, "amorce", "ligne d'amorçage après chaque changement de température"),
            self.plaque_seule,
            aide,
        ], layout=W.Layout(max_height="720px", overflow="auto")))

    def preset_petg_transparent(self):
        """Filament PETG transparent Arianeplast + réglages de base pour la transparence."""
        self._suspendu = True
        try:
            for attr, v in vars(PL.REGLAGE_TRANSPARENT).items():
                w = self.widgets.get(("Plaques", attr))
                if w is not None:
                    w.value = v
        finally:
            self._suspendu = False
        self.choix_filament.value = PL_FILAMENT       # charge le profil (Réglages › Filament)
        self.charger_filament(PL_FILAMENT)            # même s'il était déjà sélectionné
        print(f"✔ {PL_FILAMENT} : plateau {self.impression.temp_plateau} °C ; plaques : buse 245 °C, "
              "débit 1,05, 25 mm/s, ventilateur 20 %, couches 0,20 mm (vérifiez la plage indiquée sur "
              "la bobine)")

    def machine_plaques(self) -> ParametresImpression:
        """Réglages Imprimante + Filament ; température, débit, vitesse, ventilation et couche
        viennent de chaque plaque."""
        return self.impression

    def config_plaques(self) -> "PL.Plaques":
        """Plaques à imprimer d'après l'onglet (combinaisons des deux séries)."""
        variations = {}
        for menu, valeurs in self.series:
            if not menu.value:
                continue
            attr = PL.SERIES[menu.value][0]
            vals = _lire_valeurs(valeurs.value, attr)
            if vals:
                variations[attr] = vals
        return replace(self.plaques, reglages=PL.plan(self.plaque_base, **variations).reglages)

    def _maj_plaques(self):
        if not hasattr(self, "plaques_infos"):
            return
        try:
            r = PL.resume(self.config_plaques(), self.machine_plaques())
            lignes = [f"<b>{r['plaques']} plaque{'s' * (r['plaques'] > 1)}</b> · "
                      f"{r['lots']} plateau{'x' * (r['lots'] > 1)} · texte de la 1re : "
                      f"<code>{r['etiquettes'][0]}</code>"]
            p = self.impression
            couleur = "#5fc28a" if p.filament_type == "PETG" else "#e8574a"
            lignes.insert(0, f"<span style='color:{couleur}'>filament : <b>{html.escape(p.filament_nom)}</b> "
                             f"({p.filament_type}) · plateau {p.temp_plateau} °C</span> "
                             "<small>(Réglages › Filament)</small>")
            if p.filament_type != "PETG":
                lignes.insert(1, "<b style='color:#e8574a'>⚠ ces plaques sont prévues pour du PETG : "
                                 "cliquez « Préréglage PETG transparent Arianeplast »</b>")
            lignes += [f"<span style='color:#e8a33a'>⚠ {a}</span>" for a in r["alertes"]]
            self.plaques_infos.value = "<br>".join(lignes)
        except Exception as e:
            self.plaques_infos.value = f"<b style='color:#e8574a'>Erreur : {e}</b>"

    def _nom_plaques_auto(self):
        return f"plaques-petg-{datetime.now():%Y%m%d-%H%M%S}"

    def _chemin_plaques(self, ext):
        nom = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.nom_plaques.value.strip())
        return (self.dossier / f"{nom or 'plaques'}{ext}").resolve()

    def exporter_plaques(self):
        cfg = self.config_plaques()
        self._memoriser_filament()
        if self.impression.filament_type != "PETG":
            print(f"⚠ filament {self.impression.filament_nom} ({self.impression.filament_type}) : "
                  "ces plaques sont prévues pour du PETG")
        chemin = self._chemin_plaques(".gcode")
        res = PL.exporter_plaques(cfg, chemin, self.machine_plaques(), par_plaque=self.plaque_seule.value)
        for c, t in res:
            s = t.stats
            print(f"✔ G-code : {c}")
            print(f"   {s['pieces']} plaque(s) · {s['filament_m']} m · {s['masse_g']} g · "
                  + (f"{s['cout_eur']:.2f} € · " if s.get("cout_eur") else "") +
                  f"≈ {s['duree_min'] // 60} h {s['duree_min'] % 60:02d} min")
        for a in dict.fromkeys(a for _, t in res for a in t.avertissements):
            print("   ⚠", a)
        print("✔ fiche  :", PL.exporter_fiche(cfg, self._chemin_plaques(".csv"), self.machine_plaques()))
        self.trajet = res[0][1]
        return res

    def exporter_stl_plaques(self):
        for c in PL.exporter_stl_plaques(self.config_plaques(), self._chemin_plaques(".stl"), self.machine_plaques()):
            print("✔ STL    :", c)
        print("   (réglages de chaque plaque à saisir dans votre trancheur : voir la fiche CSV)")

    def _sur_plaques(self) -> bool:
        """La vue (et l'onglet Export) portent-ils sur les plaques de test ?"""
        return self.mode_vue == "plaques"

    def _changer_onglet(self, ch):
        mode = self.mode_vue
        if ch["new"] == ONGLET_PLAQUES:
            mode = "plaques"
        elif ch["new"] in ONGLETS_FORME:
            mode = "forme"
        if mode != self.mode_vue:
            self.mode_vue = mode
            self._maj_mode_export()
            self.rafraichir()

    def _maj_mode_export(self):
        if not hasattr(self, "mode_export"):
            return
        if self._sur_plaques():
            self.mode_export.value = (
                "<div style='background:#1f3a44;padding:6px 8px;border-radius:4px'>Contenu exporté : "
                "<b>plaques de test</b> (fichiers <code>" + html.escape(self._chemin_plaques("").name)
                + ".*</code>, nom "
                "réglé dans l'onglet Plaques test). Pour exporter la forme : ouvrez l'onglet "
                "<b>Forme</b>.</div>")
        else:
            self.mode_export.value = ("<small>Contenu exporté : <b>la forme</b>. Pour les plaques de "
                                      "test : ouvrez l'onglet <b>Plaques test</b>.</small>")

    def voir_plaques(self):
        """Affiche les plaques dans la vue (automatique quand l'onglet Plaques test est ouvert)."""
        from IPython.display import display

        self._maj_plaques()
        with self.sortie:
            self.sortie.clear_output(wait=True)
            fig = PL.figure_plaques(self.config_plaques(), self.machine_plaques(), titre=self.nom_plaques.value)
            fig.update_layout(height=640)
            self._derniere_figure = fig
            display(fig)
        self.infos.value = self.plaques_infos.value

    def voir_trajet_plaques(self):
        from IPython.display import display

        cfg = self.config_plaques()
        lots, _ = PL.disposer(cfg, self.machine_plaques())
        _, trajet = PL.generer_gcode_plaques(lots[0], cfg, replace(self.machine_plaques(), vignettes=()))
        with self.sortie:
            self.sortie.clear_output(wait=True)
            fig = figure_trajet(trajet, titre=f"{self.nom_plaques.value} : trajet des plaques")
            fig.update_layout(height=640)
            display(fig)

    def _maj_visibilite_klipper(self):
        if hasattr(self, "bloc_klipper"):
            self.bloc_klipper.layout.display = "" if self.impression.firmware == "klipper" else "none"

    def _onglet_export(self):
        W = self.W
        self.nom = W.Text(value=self._nom_auto(), description="nom des fichiers", style=STYLE,
                          layout=W.Layout(width=LARGEUR))
        nouveau = W.Button(description="Nouveau nom", icon="refresh", layout=W.Layout(width="150px"))
        self.mode_export = W.HTML()
        self._maj_mode_export()
        self.nom_plaques.observe(lambda _: self._maj_mode_export(), names="value")
        nouveau.on_click(lambda _: setattr(self.nom, "value", self._nom_auto()))

        def bouton(texte, icone, action, style=""):
            b = W.Button(description=texte, icon=icone, button_style=style, layout=W.Layout(width="220px"))
            b.on_click(lambda _: self._executer(action))
            return b

        tout = bouton("Tout exporter", "download", self.exporter_tout, "success")
        gcode = bouton("G-code seul", "print", self.exporter_gcode)
        stl = bouton("STL seul", "cube", self.exporter_stl)
        html = bouton("Vue 3D (HTML)", "globe", self.exporter_html)
        trajet = bouton("Voir le trajet G-code", "eye", self.voir_trajet)
        ouvrir = bouton("Ouvrir le dossier", "folder-open", self.ouvrir_dossier)

        self.choix_reglages = W.Dropdown(options=self._liste_reglages(), description="réglages",
                                         style=STYLE, layout=W.Layout(width=LARGEUR))
        sauver = bouton("Sauvegarder les réglages", "save", self.sauvegarder)
        charger = bouton("Charger", "upload", lambda: self.charger(self.choix_reglages.value))

        return W.VBox([
            self._titre("Fichiers"),
            self.mode_export,
            W.HBox([self.nom]), nouveau,
            W.HBox([tout, gcode]), W.HBox([stl, html]), W.HBox([trajet, ouvrir]),
            self._titre("Réglages"),
            W.HTML("<small>Sauvegarde tous les réglages (forme, modules, impression) sous le nom "
                   "ci-dessus, pour les recharger plus tard.</small>"),
            sauver, self.choix_reglages, charger,
            self._titre("Journal"),
            self.journal,
        ])

    # ------------------------------------------------------------------ calcul
    def generateur(self, apercu: bool = False) -> Generateur:
        base = self.base
        couches, points = APERCU[self.qualite.value] if apercu else (None, None)
        if couches:
            base = replace(base, couches=min(base.couches, couches),
                           points=max(24, min(base.points, points)))
        emb = self.emboitements.get(self.emboitement_choisi)
        return Generateur(base, list(self.deformations), emb, self.dentelle)

    def rafraichir(self):
        from IPython.display import display

        if self._sur_plaques():
            try:
                self.voir_plaques()
            except Exception as e:  # l'aperçu ne doit jamais bloquer l'interface
                self.infos.value = f"<b style='color:#e8574a'>Erreur : {e}</b>"
            return
        with self.sortie:
            self.sortie.clear_output(wait=True)
            try:
                a = self.generateur(apercu=True).generer()
                fig = figure_3d(a, titre=self.nom.value if hasattr(self, "nom") else "Forme")
                fig.update_layout(height=640)
                self._derniere_figure = fig
                display(fig)
                self.infos.value = self._resume(a)
            except Exception as e:  # l'aperçu ne doit jamais bloquer l'interface
                self.infos.value = f"<b style='color:#e8574a'>Erreur : {e}</b>"

    def _resume(self, a: Assemblage) -> str:
        mn, mx = a.pour_impression().boite()
        dims = mx - mn
        p = self.impression
        lignes = [f"<b>{len(a)} pièce{'s' * (len(a) > 1)}</b> · encombrement à l'impression "
                  f"{dims[0]:.0f} × {dims[1]:.0f} × {dims[2]:.0f} mm"]
        alertes = []
        if dims[0] > p.plateau[0] or dims[1] > p.plateau[1]:
            alertes.append(f"dépasse du plateau ({p.plateau[0]:.0f} × {p.plateau[1]:.0f} mm)")
        if dims[2] > p.hauteur_max:
            alertes.append(f"trop haute (max {p.hauteur_max:.0f} mm)")
        pire = max(_porte_a_faux(q) for q in a.pour_impression())
        if pire > p.angle_max_porte_a_faux:
            alertes.append(f"surplomb de {pire:.0f}° (> {p.angle_max_porte_a_faux:.0f}°) : "
                           "réduisez courbure, bec ou galbe")
        emb = self.emboitements.get(self.emboitement_choisi)
        if self.dentelle.actif and len(a) == 1:
            r = self.dentelle.resume(a.pour_impression().pieces[0], p.hauteur_couche)
            lignes.append(f"🕸 dentelle : {r['etages']} étages, maille ≈ {r['largeur']:.1f} × "
                          f"{r['hauteur']:.1f} mm (l × h), descentes à {r['descente_min']:.0f}°"
                          + (f"–{r['descente_max']:.0f}°" if r['descente_max'] - r['descente_min'] > 1 else "")
                          + f" (≤ {self.dentelle.angle_buse:.0f}° buse) · G-code uniquement")
            if r["etages"] == 0:
                alertes.append("pas assez de hauteur entre les bords : la paroi restera pleine")
            if not r["buse_ok"]:
                alertes.append(f"descentes à {r['descente_max']:.0f}° : le brin touchera la buse ; "
                               "étages moins hauts ou moins de cellules")
            if r["descente_min"] < 15:
                alertes.append(f"descentes très couchées ({r['descente_min']:.0f}°) : risque "
                               "d'affaissement ; plus de cellules ou des étages plus hauts")
        elif self.dentelle.actif:
            alertes.append("dentelle ignorée : elle ne s'imprime que sur une pièce unique")
        if isinstance(emb, Luminaire):
            ep = p.couches_fond * p.hauteur_couche
            lignes.append(f"💡 douille {emb.culot} ({emb.montage}) : perçage Ø {emb.diametre:.1f} mm · "
                          f"couronne {ep:.1f} mm d'épaisseur · ampoule LED uniquement")
            if ep < 1.2:
                alertes.append(f"couronne fine ({ep:.1f} mm) : montez « couches de fond » "
                               "(onglet Impression) pour la solidité")
            if emb.manchon > 0 and p.mode == "spirale":
                lignes.append("<small>le manchon impose le mode couches (pas de mode vase)</small>")
        for al in alertes:
            lignes.append(f"<span style='color:#e8a33a'>⚠ {al}</span>")
        if not alertes:
            lignes.append("<span style='color:#5fc28a'>✔ imprimable sans support</span>")
        return "<br>".join(lignes)

    # ------------------------------------------------------------------ actions
    def _executer(self, action, journal=None):
        with journal or self.journal:
            try:
                action()
            except Exception as e:
                print(f"✘ {type(e).__name__} : {e}")

    def _chemin(self, ext):
        nom = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.nom.value.strip()) or "forme"
        return self.dossier / f"{nom}{ext}"

    def exporter_html(self):
        if self._sur_plaques():
            fig = PL.figure_plaques(self.config_plaques(), self.machine_plaques(), titre=self.nom_plaques.value)
            print("✔ vue 3D :", exporter_html(fig, self._chemin_plaques(".html")))
            return
        a = self.generateur().generer()
        print("✔ vue 3D :", exporter_html(figure_3d(a, titre=self.nom.value), self._chemin(".html")))

    def exporter_stl(self):
        if self._sur_plaques():
            return self.exporter_stl_plaques()
        print("✔ STL    :", self.generateur().generer().exporter_stl(self._chemin(".stl")))
        if self.dentelle.actif:
            print("   (STL plein : la dentelle n'existe que dans le G-code)")

    def exporter_gcode(self):
        if self._sur_plaques():
            return self.exporter_plaques()[0][1]
        self._memoriser_filament()
        chemin = self._chemin(".gcode")
        self.trajet = exporter_gcode(self.generateur().generer(), chemin, self.impression)
        s = self.trajet.stats
        print(f"✔ G-code : {chemin}")
        print(f"   {s['couches']} couches · {s['filament_m']} m · {s['masse_g']} g · "
              + (f"{s['cout_eur']:.2f} € · " if s.get("cout_eur") else "") +
              f"≈ {s['duree_min'] // 60} h {s['duree_min'] % 60:02d} min · mode {s['mode']}")
        for a in self.trajet.avertissements:
            print("   ⚠", a)
        return self.trajet

    def exporter_tout(self):
        self.journal.clear_output()
        self.exporter_html()
        self.exporter_stl()
        self.exporter_gcode()

    def voir_trajet(self):
        from IPython.display import display

        if self._sur_plaques():
            self.exporter_plaques()
            return self.voir_trajet_plaques()
        trajet = self.exporter_gcode()
        with self.sortie:
            self.sortie.clear_output(wait=True)
            fig = figure_trajet(trajet, titre=f"{self.nom.value} : trajet G-code")
            fig.update_layout(height=640)
            display(fig)
        print("   (aperçu du trajet affiché ; modifiez un réglage pour revenir à la forme)")

    def ouvrir_dossier(self):
        self.dossier.mkdir(parents=True, exist_ok=True)
        chemin = self.dossier.resolve()
        if hasattr(os, "startfile"):
            os.startfile(chemin)  # Windows
        else:
            import subprocess
            import sys
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(chemin)])
        print("📂", chemin)

    def surprise(self):
        """Active 2 à 4 déformations au hasard avec des réglages modérés."""
        self._suspendu = True
        for d in self.deformations:
            self.widgets[(d.nom, "actif")].value = False
        choix = random.sample(self.deformations, random.randint(2, 4))
        for d in choix:
            defaut = type(d)()
            for n, v, m in d.parametres():
                w = self.widgets[(d.nom, n)]
                if m.get("min") is None or isinstance(v, bool):
                    continue
                v0 = getattr(defaut, n)
                etendue = 0.3 * (m["max"] - m["min"])
                x = min(max(v0 + random.uniform(-etendue, etendue), m["min"]), m["max"])
                w.value = int(round(x)) if isinstance(v, int) else round(x / m["pas"]) * m["pas"]
            self.widgets[(d.nom, "actif")].value = True
        self._suspendu = False
        self.rafraichir()
        with self.journal:
            print("🎲", ", ".join(d.nom for d in self.deformations if d.actif))

    # ------------------------------------------------------------------ réglages
    def _nom_auto(self):
        return f"forme-{datetime.now():%Y%m%d-%H%M%S}"

    def _liste_reglages(self):
        if not self.dossier_reglages.exists():
            return []
        return sorted((p.stem for p in self.dossier_reglages.glob("*.json")), reverse=True)

    def reglages(self) -> dict:
        def params(m):
            return {f.name: getattr(m, f.name) for f in fields(m)}

        return {
            "base": params(self.base),
            "deformations": [{"nom": d.nom, **params(d)} for d in self.deformations],
            "emboitement": self.emboitement_choisi,
            "emboitements": {n: params(e) for n, e in self.emboitements.items()},
            "dentelle": params(self.dentelle),
            "impression": asdict(self.impression),
        }

    def sauvegarder(self):
        self.dossier_reglages.mkdir(parents=True, exist_ok=True)
        chemin = self.dossier_reglages / f"{self._chemin('').name}.json"
        chemin.write_text(json.dumps(self.reglages(), ensure_ascii=False, indent=1), encoding="utf-8")
        self.choix_reglages.options = self._liste_reglages()
        self.choix_reglages.value = chemin.stem
        print("✔ réglages :", chemin)

    def charger(self, nom):
        if not nom:
            print("aucun réglage sauvegardé")
            return
        r = json.loads((self.dossier_reglages / f"{nom}.json").read_text(encoding="utf-8"))
        self._suspendu = True
        try:
            def regler(cle, valeurs):
                for n, v in valeurs.items():
                    w = self.widgets.get((cle, n))
                    if w is not None and n != "actif":
                        w.value = v

            regler("Base", r["base"])
            ordre = {d["nom"]: i for i, d in enumerate(r["deformations"])}
            self.deformations.sort(key=lambda d: ordre.get(d.nom, len(ordre)))
            self._ordonner_accordeon()
            for d in r["deformations"]:
                regler(d["nom"], {k: v for k, v in d.items() if k != "nom"})
                if (d["nom"], "actif") in self.widgets:
                    self.widgets[(d["nom"], "actif")].value = d["actif"]
            for n, valeurs in r["emboitements"].items():
                regler(n, valeurs)
            self.widgets[("Emboitement", "choix")].value = r["emboitement"]
            if "dentelle" in r:
                regler("Dentelle", r["dentelle"])
                self.widgets[("Dentelle", "actif")].value = r["dentelle"]["actif"]
            imp = r["impression"]
            for n, v in imp.items():
                if isinstance(v, list):
                    v = tuple(tuple(x) if isinstance(x, list) else x for x in v)
                w = self.widgets.get(("Impression", n))
                if w is not None and v is not None:
                    if isinstance(w, self.W.Dropdown) and v not in [o[1] if isinstance(o, tuple) else o
                                                                    for o in w.options]:
                        w.options = list(w.options) + [v]
                    w.value = v
                setattr(self.impression, n, v)
            self.widgets[("Impression", "plateau_x")].value = int(imp["plateau"][0])
            self.widgets[("Impression", "plateau_y")].value = int(imp["plateau"][1])
            self.widgets[("Impression", "ventilateur_pct")].value = round(imp["ventilateur"] / 2.55)
            self.widgets[("Impression", "vignettes_actives")].value = bool(imp["vignettes"])
            self.impression.ventilateur = imp["ventilateur"]
            self.nom.value = nom
        finally:
            self._suspendu = False
        self.rafraichir()
        print("✔ réglages chargés :", nom)

    # ------------------------------------------------------------------ affichage
    def afficher(self):
        from IPython.display import display

        display(self.vue)
        return self

    def _ipython_display_(self):
        from IPython.display import display

        display(self.vue)


def _defilant(boite):
    """Empêche les enfants d'une boîte qui défile d'être écrasés à hauteur nulle.

    Dans une VBox limitée en hauteur (``max_height`` + ``overflow``), flexbox rétrécit les
    enfants au lieu de faire défiler : les rangées de boutons disparaissent.
    """
    for enfant in boite.children:
        enfant.layout.flex = "0 0 auto"
    return boite


def _lire_valeurs(texte: str, attr: str) -> list:
    """« 235 240 245 », « 1,05 ; 1,10 » ou « 1.00, 1.05 » → liste typée selon le paramètre."""
    import re

    morceaux = [m for m in re.split(r"[;\s]+|,\s+", texte.strip()) if m]
    if attr == "motif":
        inconnus = [m for m in morceaux if m not in PL.MOTIFS]
        if inconnus:
            raise ValueError(f"lignes inconnues : {', '.join(inconnus)} ({' | '.join(PL.MOTIFS)})")
        return morceaux
    vals = [float(m.replace(",", ".")) for m in morceaux]
    if attr in ("temp_buse", "ventilateur"):
        return [int(round(v)) for v in vals]
    return vals


def application(dossier="sorties") -> Application:
    """Crée l'application (affichée comme résultat de la cellule).

    Les fichiers sont écrits dans ``dossier``.
    """
    return Application(dossier)
