import json

from ville.cerveau.plan import LIEU_TRAVAIL, EtapePlan
from ville.configuration import ConfigurationCerveau
from ville.moteur.agent import ATTENTE, LOISIR, TRAVAIL

ACTIVITES = (ATTENTE, LOISIR, TRAVAIL)


class ReponseInvalide(Exception):
    pass


def schema_plan(lieux: dict[str, int], cerveau: ConfigurationCerveau) -> dict:
    return {
        "type": "object",
        "properties": {
            "etapes": {
                "type": "array",
                "minItems": 1,
                "maxItems": cerveau.etapes_max,
                "items": {
                    "type": "object",
                    "properties": {
                        "lieu": {"type": "string", "enum": sorted(lieux)},
                        "activite": {"type": "string", "enum": list(ACTIVITES)},
                        "duree_minutes": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": cerveau.duree_max_minutes,
                        },
                    },
                    "required": ["lieu", "activite", "duree_minutes"],
                },
            }
        },
        "required": ["etapes"],
    }


def analyser_plan(
    texte: str, lieux: dict[str, int], cerveau: ConfigurationCerveau
) -> list[EtapePlan]:
    try:
        contenu = json.loads(texte)
    except ValueError as erreur:
        raise ReponseInvalide("réponse qui n'est pas du JSON") from erreur
    if not isinstance(contenu, dict) or not isinstance(contenu.get("etapes"), list):
        raise ReponseInvalide("champ « etapes » absent")
    etapes = contenu["etapes"]
    if not 1 <= len(etapes) <= cerveau.etapes_max:
        raise ReponseInvalide(f"nombre d'étapes invalide : {len(etapes)}")
    return [_analyser_etape(etape, lieux, cerveau) for etape in etapes]


def _analyser_etape(
    etape: object, lieux: dict[str, int], cerveau: ConfigurationCerveau
) -> EtapePlan:
    if not isinstance(etape, dict):
        raise ReponseInvalide("étape qui n'est pas un objet")
    lieu, activite, duree = etape.get("lieu"), etape.get("activite"), etape.get("duree_minutes")
    if not isinstance(lieu, str) or lieu not in lieux:
        raise ReponseInvalide(f"lieu inconnu : {lieu!r}")
    if activite not in ACTIVITES:
        raise ReponseInvalide(f"activité inconnue : {activite!r}")
    if type(duree) is not int or not 1 <= duree <= cerveau.duree_max_minutes:
        raise ReponseInvalide(f"durée invalide : {duree!r}")
    if activite == TRAVAIL and lieu != LIEU_TRAVAIL:
        raise ReponseInvalide(f"travail impossible au lieu : {lieu}")
    return EtapePlan(lieu, activite, duree)
