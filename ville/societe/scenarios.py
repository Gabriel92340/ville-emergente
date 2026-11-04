import json
from pathlib import Path

PLUIE_ARGENT = "pluie_argent"
RUMEUR = "rumeur"
ELECTION = "election"


class ScenarioInvalide(ValueError):
    pass


def _entier_positif(evenement: dict, champ: str) -> int:
    valeur = evenement.get(champ)
    if type(valeur) is not int or valeur < 0:
        raise ScenarioInvalide(f"champ « {champ} » invalide : {evenement}")
    return valeur


def _valider(evenement: object, nb_agents: int) -> None:
    if not isinstance(evenement, dict):
        raise ScenarioInvalide(f"événement qui n'est pas un objet : {evenement}")
    _entier_positif(evenement, "tick")
    nature = evenement.get("type")
    if nature == PLUIE_ARGENT:
        _entier_positif(evenement, "montant_centimes")
    elif nature == RUMEUR:
        if not isinstance(evenement.get("contenu"), str) or not evenement["contenu"]:
            raise ScenarioInvalide(f"rumeur sans contenu : {evenement}")
        if _entier_positif(evenement, "source") >= nb_agents:
            raise ScenarioInvalide(f"source inconnue : {evenement}")
    elif nature == ELECTION:
        if _entier_positif(evenement, "tick_vote") <= evenement["tick"]:
            raise ScenarioInvalide(f"vote antérieur à l'ouverture : {evenement}")
        candidats = evenement.get("candidats")
        if not isinstance(candidats, list) or len(candidats) < 2:
            raise ScenarioInvalide(f"il faut au moins deux candidats : {evenement}")
        for candidat in candidats:
            if not isinstance(candidat, dict):
                raise ScenarioInvalide(f"candidat invalide : {candidat}")
            if _entier_positif(candidat, "agent") >= nb_agents:
                raise ScenarioInvalide(f"candidat inconnu : {candidat}")
            if _entier_positif(candidat, "taux_impot_pourcent") > 100:
                raise ScenarioInvalide(f"taux d'impôt invalide : {candidat}")
    else:
        raise ScenarioInvalide(f"type d'événement inconnu : {nature}")


def valider_scenario(evenements: list[dict], nb_agents: int) -> list[dict]:
    for evenement in evenements:
        _valider(evenement, nb_agents)
    return sorted(evenements, key=lambda evenement: evenement["tick"])


def charger_scenario(chemin: str | Path) -> list[dict]:
    with open(chemin, encoding="utf-8") as fichier:
        contenu = json.load(fichier)
    if not isinstance(contenu, list):
        raise ScenarioInvalide(f"un scénario est une liste d'événements : {chemin}")
    return contenu
