import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ville.cerveau.client import ClientFactice, ClientOllama, DemandeModele, ErreurModele


def demande(**champs) -> DemandeModele:
    base = {
        "agent": 3,
        "tick": 12,
        "prompt": "Bonjour é",
        "graine": 77,
        "modele": "essai:1b",
        "temperature": 0.5,
        "nb_jetons_max": 50,
        "schema": {"type": "object"},
    }
    return DemandeModele(**{**base, **champs})


@pytest.fixture
def serveur():
    etat = {"statut": 200, "corps": b'{"response":"texte"}', "recu": None, "chemin": None}

    class Gestionnaire(BaseHTTPRequestHandler):
        def do_POST(self):
            longueur = int(self.headers["Content-Length"])
            etat["recu"] = json.loads(self.rfile.read(longueur).decode("utf-8"))
            etat["chemin"] = self.path
            self.send_response(etat["statut"])
            self.end_headers()
            self.wfile.write(etat["corps"])

        def log_message(self, *arguments):
            pass

    instance = HTTPServer(("127.0.0.1", 0), Gestionnaire)
    fil = threading.Thread(target=instance.serve_forever, daemon=True)
    fil.start()
    yield etat, f"http://127.0.0.1:{instance.server_port}"
    instance.shutdown()
    instance.server_close()


def test_envoie_modele_graine_et_schema(serveur):
    etat, url = serveur
    assert ClientOllama(url).generer(demande()) == "texte"
    assert etat["chemin"] == "/api/generate"
    assert etat["recu"] == {
        "model": "essai:1b",
        "prompt": "Bonjour é",
        "stream": False,
        "format": {"type": "object"},
        "options": {"seed": 77, "temperature": 0.5, "num_predict": 50},
    }


@pytest.mark.parametrize(
    "statut,corps",
    [
        (500, b"panne"),
        (404, b'{"error":"modele inconnu"}'),
        (200, b"pas du json"),
        (200, b"[1,2]"),
        (200, b'{"response":12}'),
        (200, b"{}"),
    ],
)
def test_reponse_inexploitable_donne_une_erreur_modele(serveur, statut, corps):
    etat, url = serveur
    etat["statut"], etat["corps"] = statut, corps
    with pytest.raises(ErreurModele):
        ClientOllama(url).generer(demande())


def test_serveur_absent_donne_une_erreur_modele():
    with pytest.raises(ErreurModele, match="appel au modèle impossible"):
        ClientOllama("http://127.0.0.1:9", delai_max_s=2).generer(demande())


def test_client_factice_note_les_demandes():
    client = ClientFactice(lambda d: f"graine {d.graine}")
    assert client.generer(demande()) == "graine 77"
    assert [d.agent for d in client.demandes] == [3]
