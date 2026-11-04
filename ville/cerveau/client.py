import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol


class ErreurModele(Exception):
    pass


@dataclass(frozen=True)
class DemandeModele:
    agent: int
    tick: int
    prompt: str
    graine: int
    modele: str
    temperature: float
    nb_jetons_max: int
    schema: dict


class Client(Protocol):
    def generer(self, demande: DemandeModele) -> str: ...


def _est_coupure_de_connexion(erreur: Exception) -> bool:
    if isinstance(erreur, urllib.error.HTTPError):
        return False
    if isinstance(erreur, urllib.error.URLError):
        return isinstance(erreur.reason, OSError) and not isinstance(erreur.reason, TimeoutError)
    return isinstance(erreur, ConnectionError)


class ClientOllama:
    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        delai_max_s: float = 120.0,
        pause_reessai_s: float = 2.0,
    ):
        self._url = url.rstrip("/")
        self._delai_max_s = delai_max_s
        self._pause_reessai_s = pause_reessai_s

    def generer(self, demande: DemandeModele) -> str:
        corps = json.dumps(
            {
                "model": demande.modele,
                "prompt": demande.prompt,
                "stream": False,
                "format": demande.schema,
                "options": {
                    "seed": demande.graine,
                    "temperature": demande.temperature,
                    "num_predict": demande.nb_jetons_max,
                },
            }
        ).encode("utf-8")
        requete = urllib.request.Request(
            f"{self._url}/api/generate",
            data=corps,
            headers={"Content-Type": "application/json"},
        )
        try:
            contenu = self._envoyer(requete)
        except (OSError, ValueError) as erreur:
            if not _est_coupure_de_connexion(erreur):
                raise ErreurModele(f"appel au modèle impossible : {erreur}") from erreur
            time.sleep(self._pause_reessai_s)
            try:
                contenu = self._envoyer(requete)
            except (OSError, ValueError) as seconde_erreur:
                raise ErreurModele(
                    f"appel au modèle impossible : {seconde_erreur}"
                ) from seconde_erreur
        if not isinstance(contenu, dict) or not isinstance(contenu.get("response"), str):
            raise ErreurModele("réponse d'Ollama sans champ « response »")
        return contenu["response"]

    def _envoyer(self, requete: urllib.request.Request) -> object:
        with urllib.request.urlopen(requete, timeout=self._delai_max_s) as reponse:
            return json.loads(reponse.read().decode("utf-8"))


class ClientFactice:
    def __init__(self, fonction: Callable[[DemandeModele], str], latence_s: float = 0.0):
        self._fonction = fonction
        self._latence_s = latence_s
        self.demandes: list[DemandeModele] = []

    def generer(self, demande: DemandeModele) -> str:
        self.demandes.append(demande)
        if self._latence_s:
            time.sleep(self._latence_s)
        return self._fonction(demande)
