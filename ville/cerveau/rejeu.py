import json
from pathlib import Path

from ville.cerveau.client import DemandeModele, ErreurModele
from ville.configuration import Configuration, ConfigurationCerveau


class RejeuDivergent(Exception):
    pass


def lire_entete(chemin: str | Path) -> dict:
    with open(chemin, encoding="utf-8") as fichier:
        entete = json.loads(fichier.readline())
    if entete.get("type") != "entete" or "cerveau" not in entete:
        raise RejeuDivergent(f"journal sans en-tête de cerveau : {chemin}")
    return entete


def configurations_du_journal(entete: dict) -> tuple[Configuration, ConfigurationCerveau]:
    parametres = {cle: valeur for cle, valeur in entete["cerveau"].items() if cle != "version_prompt"}
    return Configuration(**entete["configuration"]), ConfigurationCerveau(**parametres)


class ClientRejeu:
    def __init__(self, chemin: str | Path):
        self._reflexions: dict[tuple[int, int], dict] = {}
        with open(chemin, encoding="utf-8") as fichier:
            for ligne in fichier:
                evenement = json.loads(ligne)
                if evenement["type"] == "reflexion":
                    self._reflexions[(evenement["tick_demande"], evenement["agent"])] = evenement

    def generer(self, demande: DemandeModele) -> str:
        cle = (demande.tick, demande.agent)
        if cle not in self._reflexions:
            raise RejeuDivergent(f"aucune réponse journalisée pour {cle}")
        reflexion = self._reflexions[cle]
        if reflexion["contexte"] != demande.prompt:
            raise RejeuDivergent(f"prompt différent du journal pour {cle}")
        if reflexion["graine_modele"] != demande.graine or reflexion["modele"] != demande.modele:
            raise RejeuDivergent(f"graine ou modèle différent du journal pour {cle}")
        if reflexion["erreur"] is not None and reflexion["reponse_brute"] is None:
            raise ErreurModele(reflexion["erreur"])
        return reflexion["reponse_brute"]
