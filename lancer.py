"""Lance l'application dans le navigateur (Voilà), sans code visible.

Démarre le serveur Voilà, attend qu'il réponde puis ouvre le navigateur.
Arrêt : Ctrl + C (ou fermer la fenêtre du terminal).
"""

import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
NOTEBOOK = "generateur_formes.ipynb"


def port_libre(depart=8866):
    for port in range(depart, depart + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("aucun port libre entre 8866 et 8915")


def attendre(url, delai=180):
    fin = time.time() + delai
    while time.time() < fin:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    try:
        import voila  # noqa: F401
    except ImportError:
        sys.exit("Voilà n'est pas installé : lancez d'abord\n"
                 f"  {sys.executable} -m pip install -r requirements.txt")
    port = port_libre()
    url = f"http://localhost:{port}/"
    print(f"Démarrage de l'application sur {url} …")
    serveur = subprocess.Popen([sys.executable, "-m", "voila", NOTEBOOK, "--no-browser",
                                f"--port={port}", "--Voila.ip=127.0.0.1"], cwd=DOSSIER)
    try:
        if attendre(url) and serveur.poll() is None:
            print(f"\nApplication prête : {url}")
            print("Si le navigateur ne s'ouvre pas, copiez cette adresse dans la barre d'adresse.")
            print("Pour arrêter : Ctrl + C ou fermez cette fenêtre.\n")
            webbrowser.open(url)
        else:
            print("Le serveur n'a pas démarré (voir les messages ci-dessus).")
        serveur.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if serveur.poll() is None:
            serveur.terminate()


if __name__ == "__main__":
    main()
