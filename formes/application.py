"""Application graphique complète (ipywidgets) : aucune saisie de code.

Tout se règle avec des menus, curseurs, cases et boutons :

- **Forme**        : profil de base et ses dimensions ;
- **Déformations** : chaque module s'active d'une case, se règle aux curseurs
                     et se déplace dans l'ordre d'application (↑ / ↓) ;
- **Emboîtement**  : choix par boutons radio ;
- **Impression**   : préréglages d'imprimante et de filament, firmware, mode,
                     options Klipper (macros, purge, maillage adaptatif…) ;
- **Export**       : HTML, STL et G-code en un clic, sauvegarde des réglages.

Lancement dans un notebook ::

    from formes.application import application
    application()

ou, sans aucun code visible : ``python -m voila generateur_formes.ipynb``.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, fields, replace
from datetime import datetime
from pathlib import Path

from .bases import PROFILS, Base
from .deformations import TOUTES, Fuseau, Torsion
from .emboitements import TOUS
from .gcode import ParametresImpression, _porte_a_faux, exporter_gcode
from .generateur import Generateur
from .geometrie import Assemblage
from .visualisation import figure_3d, figure_trajet, exporter_html

# ---------------------------------------------------------------------------
# Préréglages
# ---------------------------------------------------------------------------

IMPRIMANTES = {
    "Personnalisée": None,
    "Voron 2.4 – 350": dict(plateau=(350.0, 350.0), hauteur_max=340.0, firmware="klipper"),
    "Voron 2.4 – 300": dict(plateau=(300.0, 300.0), hauteur_max=290.0, firmware="klipper"),
    "Voron Trident – 300": dict(plateau=(300.0, 300.0), hauteur_max=250.0, firmware="klipper"),
    "Voron 0.2 – 120": dict(plateau=(120.0, 120.0), hauteur_max=120.0, firmware="klipper"),
    "Creality K1 / K1C": dict(plateau=(220.0, 220.0), hauteur_max=250.0, firmware="klipper"),
    "Sovol SV06 Plus / SV07 (Klipper)": dict(plateau=(300.0, 300.0), hauteur_max=340.0, firmware="klipper"),
    "Ender 3 / Ender 3 V2 (Marlin)": dict(plateau=(220.0, 220.0), hauteur_max=250.0, firmware="marlin"),
    "Ender 3 + Klipper": dict(plateau=(220.0, 220.0), hauteur_max=250.0, firmware="klipper"),
    "Prusa MK3S / MK4 (Marlin)": dict(plateau=(250.0, 210.0), hauteur_max=210.0, firmware="marlin"),
}

FILAMENTS = {
    "PLA":  dict(temp_buse=210, temp_plateau=60, densite_g_cm3=1.24, ventilateur=255),
    "PETG": dict(temp_buse=235, temp_plateau=80, densite_g_cm3=1.27, ventilateur=128),
    "ABS":  dict(temp_buse=245, temp_plateau=100, densite_g_cm3=1.04, ventilateur=0),
    "ASA":  dict(temp_buse=250, temp_plateau=100, densite_g_cm3=1.07, ventilateur=0),
    "TPU":  dict(temp_buse=225, temp_plateau=50, densite_g_cm3=1.21, ventilateur=128),
}

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
}

APERCU = {"Rapide": (60, 144), "Normal": (120, 240), "Fin": (None, None)}

STYLE = {"description_width": "150px"}
LARGEUR = "460px"


def _curseur(nom, valeur, meta, description=None):
    """Curseur adapté au type de la valeur et aux bornes de ``param(...)``."""
    import ipywidgets as W

    commun = dict(description=description or nom.replace("_", " "), style=STYLE,
                  layout=W.Layout(width="98%", max_width=LARGEUR), continuous_update=False)
    if isinstance(valeur, bool):
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
        self.impression = ParametresImpression()
        self.widgets: dict[tuple[str, str], W.Widget] = {}

        # -- construction ---------------------------------------------------------
        self.sortie = W.Output(layout=W.Layout(width="100%"))
        self.infos = W.HTML()
        self.journal = W.Output(layout=W.Layout(width=LARGEUR, max_height="260px", overflow="auto"))

        onglets = W.Tab(children=[self._onglet_forme(), self._onglet_deformations(),
                                  self._onglet_emboitement(), self._onglet_impression(),
                                  self._onglet_export()])
        for i, t in enumerate(["Forme", "Déformations", "Emboîtement", "Impression", "Export"]):
            onglets.set_title(i, t)
        onglets.layout = W.Layout(width="500px")

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
            W.HBox([W.VBox([barre, onglets], layout=W.Layout(flex="0 0 510px", width="510px")),
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

    def _onglet_impression(self):
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

        # préréglages : ils modifient les curseurs, qui modifient les paramètres
        imprimante = menu("imprimante", list(IMPRIMANTES), "Personnalisée", "imprimante")
        filament = menu("filament", list(FILAMENTS), "PLA", "filament")

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

        def appliquer_preset(valeurs):
            self._suspendu = True
            for attr, v in valeurs.items():
                if attr == "plateau":
                    plateau_x.value, plateau_y.value = int(v[0]), int(v[1])
                elif ("Impression", attr) in self.widgets:
                    self.widgets[("Impression", attr)].value = v
                else:
                    setattr(p, attr, v)
            self._suspendu = False
            self.rafraichir()

        imprimante.observe(lambda ch: IMPRIMANTES[ch["new"]] and appliquer_preset(IMPRIMANTES[ch["new"]]),
                           names="value")

        def choisir_filament(ch):
            p.filament_type = p.filament_nom = ch["new"]
            appliquer_preset(FILAMENTS[ch["new"]])

        filament.observe(choisir_filament, names="value")

        buse = W.Dropdown(options=[0.2, 0.25, 0.4, 0.5, 0.6, 0.8, 1.0], value=p.diametre_buse,
                          description="buse (mm)", style=STYLE, layout=lay)
        self._lier(p, "diametre_buse", buse, "Impression",
                   apres=lambda: setattr(self.widgets[("Impression", "largeur_ligne")], "value",
                                         round(1.125 * p.diametre_buse, 2)))

        vent = W.IntSlider(value=round(p.ventilateur / 2.55), min=0, max=100, step=5,
                           description="ventilateur (%)", style=STYLE, layout=lay, continuous_update=False)
        self.widgets[("Impression", "ventilateur_pct")] = vent
        vent.observe(lambda ch: setattr(p, "ventilateur", round(ch["new"] * 2.55)), names="value")

        couleur = W.ColorPicker(value=p.filament_couleur, description="couleur (Mainsail)",
                                style=STYLE, layout=lay)
        self._lier(p, "filament_couleur", couleur, "Impression")

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
                   "et choisissez « Aucune » pour la purge.</small>"),
        ])

        vignettes = W.Checkbox(value=bool(p.vignettes), description="vignettes d'aperçu (Mainsail)",
                               indent=False)
        self.widgets[("Impression", "vignettes_actives")] = vignettes
        vignettes.observe(lambda ch: setattr(p, "vignettes", ((32, 32), (300, 300)) if ch["new"] else ()),
                          names="value")

        return W.VBox([
            self._titre("Machine"),
            imprimante,
            bascule("firmware", ["klipper", "marlin"], "firmware", apres=self._maj_visibilite_klipper),
            plateau_x, plateau_y,
            curseur("hauteur_max", 50, 600, 5, "hauteur max (mm)"),
            buse,
            self._titre("Filament"),
            filament,
            curseur("temp_buse", 170, 300, 5, "buse (°C)"),
            curseur("temp_plateau", 0, 120, 5, "plateau (°C)"),
            couleur,
            self._lier(p, "diametre_filament",
                       W.Dropdown(options=[1.75, 2.85], value=p.diametre_filament, description="Ø filament (mm)",
                                  style=STYLE, layout=lay), "Impression"),
            self._titre("Tranchage"),
            bascule("mode", ["spirale", "couches"], "mode"),
            W.HTML("<small>spirale = mode vase (une pièce, sans couture) ; plusieurs pièces → couches "
                   "automatiquement.</small>"),
            curseur("hauteur_couche", 0.08, 0.6, 0.02, "hauteur de couche (mm)"),
            curseur("largeur_ligne", 0.2, 1.4, 0.01, "largeur de ligne (mm)"),
            curseur("couches_fond", 0, 15, 1, "couches de fond"),
            curseur("flux", 0.8, 1.2, 0.01, "flux"),
            curseur("vitesse", 5, 150, 1, "vitesse parois (mm/s)"),
            curseur("vitesse_premiere_couche", 5, 60, 1, "vitesse 1re couche"),
            curseur("vitesse_remplissage", 5, 200, 1, "vitesse fond (mm/s)"),
            curseur("vitesse_deplacement", 30, 500, 10, "vitesse déplacements"),
            curseur("retraction", 0, 8, 0.1, "rétraction (mm)"),
            vent,
            vignettes,
            self.bloc_klipper,
        ], layout=W.Layout(max_height="720px", overflow="auto"))

    def _maj_visibilite_klipper(self):
        if hasattr(self, "bloc_klipper"):
            self.bloc_klipper.layout.display = "" if self.impression.firmware == "klipper" else "none"

    def _onglet_export(self):
        W = self.W
        self.nom = W.Text(value=self._nom_auto(), description="nom des fichiers", style=STYLE,
                          layout=W.Layout(width=LARGEUR))
        nouveau = W.Button(description="Nouveau nom", icon="refresh", layout=W.Layout(width="150px"))
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
        return Generateur(base, list(self.deformations), emb)

    def rafraichir(self):
        from IPython.display import display

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
        for al in alertes:
            lignes.append(f"<span style='color:#e8a33a'>⚠ {al}</span>")
        if not alertes:
            lignes.append("<span style='color:#5fc28a'>✔ imprimable sans support</span>")
        return "<br>".join(lignes)

    # ------------------------------------------------------------------ actions
    def _executer(self, action):
        with self.journal:
            try:
                action()
            except Exception as e:
                print(f"✘ {type(e).__name__} : {e}")

    def _chemin(self, ext):
        nom = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.nom.value.strip()) or "forme"
        return self.dossier / f"{nom}{ext}"

    def exporter_html(self):
        a = self.generateur().generer()
        print("✔ vue 3D :", exporter_html(figure_3d(a, titre=self.nom.value), self._chemin(".html")))

    def exporter_stl(self):
        print("✔ STL    :", self.generateur().generer().exporter_stl(self._chemin(".stl")))

    def exporter_gcode(self):
        chemin = self._chemin(".gcode")
        self.trajet = exporter_gcode(self.generateur().generer(), chemin, self.impression)
        s = self.trajet.stats
        print(f"✔ G-code : {chemin}")
        print(f"   {s['couches']} couches · {s['filament_m']} m · {s['masse_g']} g · "
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
            imp = r["impression"]
            for n, v in imp.items():
                if isinstance(v, list):
                    v = tuple(tuple(x) if isinstance(x, list) else x for x in v)
                w = self.widgets.get(("Impression", n))
                if w is not None:
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


def application(dossier="sorties") -> Application:
    """Crée l'application (affichée comme résultat de la cellule).

    Les fichiers sont écrits dans ``dossier``.
    """
    return Application(dossier)
