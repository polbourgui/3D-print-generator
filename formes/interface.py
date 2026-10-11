"""Panneau interactif ipywidgets : une case à cocher et des curseurs par module.

Les curseurs sont générés automatiquement à partir des bornes déclarées par
``param(...)`` dans chaque module : ajouter un nouveau module suffit à le
rendre pilotable depuis le notebook.
"""

from __future__ import annotations

from .bases import PROFILS
from .generateur import Generateur


def _widget(module, nom, valeur, meta, rafraichir):
    import ipywidgets as W

    style = {"description_width": "150px"}
    layout = W.Layout(width="440px")
    if nom == "profil":
        w = W.Dropdown(options=PROFILS, value=valeur, description=nom, style=style, layout=layout)
    elif isinstance(valeur, bool):
        w = W.Checkbox(value=valeur, description=nom)
    elif isinstance(valeur, int):
        w = W.IntSlider(value=valeur, min=meta.get("min") or 0, max=meta.get("max") or 100,
                        step=int(meta.get("pas") or 1), description=nom, style=style, layout=layout,
                        continuous_update=False)
    else:
        w = W.FloatSlider(value=valeur, min=meta.get("min") or 0.0, max=meta.get("max") or 100.0,
                          step=meta.get("pas") or 0.1, description=nom, style=style, layout=layout,
                          continuous_update=False)
    if meta.get("aide"):
        w.description_tooltip = meta["aide"]

    def changer(ch):
        setattr(module, nom, ch["new"])
        rafraichir()

    w.observe(changer, names="value")
    return w


def panneau(gen: Generateur, rendu):
    """Construit le panneau ; ``rendu(gen)`` est rappelée à chaque changement.

    ``rendu`` doit renvoyer une figure Plotly (affichée dans le panneau).
    """
    import ipywidgets as W
    from IPython.display import display

    sortie = W.Output()

    def rafraichir():
        with sortie:
            sortie.clear_output(wait=True)
            display(rendu(gen))

    def bloc(module, titre, activable=True):
        enfants = [_widget(module, n, v, m, rafraichir) for n, v, m in module.parametres()]
        if activable:
            case = W.Checkbox(value=module.actif, description="actif", indent=False)
            corps = W.VBox(enfants, layout=W.Layout(display="" if module.actif else "none"))

            def basculer(ch):
                module.actif = ch["new"]
                corps.layout.display = "" if ch["new"] else "none"
                rafraichir()

            case.observe(basculer, names="value")
            enfants = [case, corps]
        return W.VBox(enfants), titre

    blocs = [bloc(gen.base, "Base", activable=False)]
    blocs += [bloc(d, f"{i + 1}. {d.nom}") for i, d in enumerate(gen.deformations)]
    if gen.emboitement is not None:
        blocs.append(bloc(gen.emboitement, f"Emboîtement : {gen.emboitement.nom}"))

    acc = W.Accordion(children=[b for b, _ in blocs])
    for i, (_, t) in enumerate(blocs):
        acc.set_title(i, t)
    rafraichir()
    return W.HBox([W.Box([acc], layout=W.Layout(width="480px", overflow="auto", max_height="680px")),
                   sortie])
