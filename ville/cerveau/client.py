import json
import time
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


class ClientOllama:
    def __init__(self, url: str = "http://127.0.0.1:11434", delai_max_s: float = 120.0):
        self._url = url.rstrip("/")
        self._delai_max_s = delai_max_s

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
            with urllib.request.urlopen(requete, timeout=self._delai_max_s) as reponse:
                contenu = json.loads(reponse.read().decode("utf-8"))
        except (OSError, ValueError) as erreur:
            raise ErreurModele(f"appel au modèle impossible : {erreur}") from erreur
        if not isinstance(contenu, dict) or not isinstance(contenu.get("response"), str):
            raise ErreurModele("réponse d'Ollama sans champ « response »")
        return contenu["response"]


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
