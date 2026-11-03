from ville.cerveau.memoire import Memoire
from ville.configuration import Configuration, ConfigurationCerveau
from ville.moteur.agent import Perception

VERSION_PROMPT = "1"


def heure_lisible(seconde_du_jour: int) -> str:
    return f"{seconde_du_jour // 3600:02d}h{seconde_du_jour % 3600 // 60:02d}"


def euros(centimes: int) -> str:
    return f"{centimes // 100},{centimes % 100:02d} €"


def _position(perception: Perception, lieux: dict[str, int]) -> str:
    for nom in sorted(lieux):
        if lieux[nom] == perception.noeud:
            return nom
    return "dans la rue"


def construire_prompt(
    perception: Perception,
    lieux: dict[str, int],
    memoire: Memoire,
    configuration: Configuration,
    cerveau: ConfigurationCerveau,
) -> str:
    souvenirs = "\n".join(f"- {souvenir}" for souvenir in memoire.souvenirs) or "- aucun"
    faits = ", ".join(f"{fait} : {nombre}" for fait, nombre in memoire.faits) or "aucun"
    return (
        f"Tu es l'habitant n°{perception.agent} d'une ville.\n"
        f"Il est {heure_lisible(perception.seconde_du_jour)}. "
        f"Ton budget est de {euros(perception.budget_centimes)}. "
        f"Tu es : {_position(perception, lieux)}.\n"
        f"Lieux que tu connais : {', '.join(sorted(lieux))}.\n"
        f"Le travail n'est possible qu'au lieu « travail » et rapporte "
        f"{euros(configuration.salaire_horaire_centimes)} de l'heure. "
        f"Un loisir coûte {euros(configuration.prix_loisir_centimes)}.\n"
        f"Compteurs : {faits}.\n"
        f"Souvenirs récents :\n{souvenirs}\n"
        f"Écris ton plan pour les prochaines heures, en {cerveau.etapes_max} étapes au plus. "
        f"Chaque étape indique un lieu, une activité (travail, loisir ou attente) "
        f"et une durée en minutes, de 1 à {cerveau.duree_max_minutes}.\n"
        f'Réponds uniquement en JSON : {{"etapes":[{{"lieu":"...","activite":"...",'
        f'"duree_minutes":60}}]}}'
    )
