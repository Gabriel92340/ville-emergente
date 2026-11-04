import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ville.cerveau.client import Client, ClientOllama, DemandeModele, ErreurModele
from ville.cerveau.memoire import Memoire
from ville.cerveau.prompts import construire_prompt
from ville.cerveau.reponses import ReponseInvalide, analyser_plan, schema_plan
from ville.configuration import Configuration, ConfigurationCerveau
from ville.moteur.agent import Perception

LIEUX_EXEMPLE = {"domicile": 1, "travail": 2, "loisir_1": 3, "loisir_2": 4, "loisir_3": 5}


@dataclass(frozen=True)
class Contexte:
    seconde_du_jour: int
    noeud: int
    souvenirs: tuple[str, ...]
    faits: tuple[str, ...]


CONTEXTES = {
    "matin": Contexte(8 * 3600, 1, (), ()),
    "soir": Contexte(
        18 * 3600 + 30 * 60,
        3,
        ("09h10 : arrivé (travail)", "09h10 : travail pendant 480 min", "17h20 : arrivé (loisir)"),
        ("travail", "travail", "travail", "loisir"),
    ),
}


def demande_exemple(cerveau: ConfigurationCerveau, contexte: str, graine: int) -> DemandeModele:
    situation = CONTEXTES[contexte]
    perception = Perception(
        tick=0,
        seconde_du_jour=situation.seconde_du_jour,
        agent=0,
        noeud=situation.noeud,
        etape="initial",
        budget_centimes=10000,
        domicile=1,
        travail=2,
        heure_travail_s=8 * 3600,
    )
    memoire = Memoire(cerveau.taille_memoire)
    for souvenir in situation.souvenirs:
        memoire.retenir(souvenir)
    for fait in situation.faits:
        memoire.compter(fait)
    return DemandeModele(
        agent=0,
        tick=0,
        prompt=construire_prompt(perception, LIEUX_EXEMPLE, memoire, Configuration(), cerveau),
        graine=graine,
        modele=cerveau.modele,
        temperature=cerveau.temperature,
        nb_jetons_max=cerveau.nb_jetons_max,
        schema=schema_plan(LIEUX_EXEMPLE, cerveau),
    )


def mesurer_sequentiel(
    client: Client, cerveau: ConfigurationCerveau, contexte: str, essais: int
) -> dict:
    latences, valides, erreurs, reponses = [], 0, 0, set()
    for graine in range(essais):
        debut = time.perf_counter()
        try:
            texte = client.generer(demande_exemple(cerveau, contexte, graine))
            reponses.add(texte)
            analyser_plan(texte, LIEUX_EXEMPLE, cerveau)
            valides += 1
        except ReponseInvalide:
            pass
        except ErreurModele:
            erreurs += 1
        latences.append(time.perf_counter() - debut)
    latences.sort()
    return {
        "contexte": contexte,
        "essais": essais,
        "valides": valides,
        "erreurs": erreurs,
        "reponses_distinctes": len(reponses),
        "latence_mediane_s": round(latences[len(latences) // 2], 3),
        "latence_max_s": round(latences[-1], 3),
    }


def mesurer_stabilite(
    client: Client, cerveau: ConfigurationCerveau, contexte: str, essais: int
) -> dict:
    demande = demande_exemple(cerveau, contexte, 1234)
    meme_graine = {client.generer(demande) for _ in range(essais)}
    entre_graines = {
        client.generer(demande_exemple(cerveau, contexte, graine)) for graine in range(essais)
    }
    return {
        "contexte": contexte,
        "repetitions": essais,
        "reponses_distinctes_meme_graine": len(meme_graine),
        "reponses_distinctes_entre_graines": len(entre_graines),
    }


def mesurer_debit(client: Client, cerveau: ConfigurationCerveau, ouvriers: int, appels: int) -> dict:
    demandes = [demande_exemple(cerveau, "soir", graine) for graine in range(appels)]
    debut = time.perf_counter()
    with ThreadPoolExecutor(max_workers=ouvriers) as executeur:
        list(executeur.map(client.generer, demandes))
    duree = time.perf_counter() - debut
    return {"ouvriers": ouvriers, "appels": appels, "appels_par_seconde": round(appels / duree, 3)}


def main() -> None:
    analyseur = argparse.ArgumentParser(description="Mesurer le modèle local")
    analyseur.add_argument("--modele", default=ConfigurationCerveau.modele)
    analyseur.add_argument("--url-ollama", default="http://127.0.0.1:11434")
    analyseur.add_argument("--essais", type=int, default=30)
    arguments = analyseur.parse_args()
    cerveau = ConfigurationCerveau(modele=arguments.modele)
    client = ClientOllama(arguments.url_ollama)
    client.generer(demande_exemple(cerveau, "matin", 0))
    for contexte in CONTEXTES:
        print(mesurer_sequentiel(client, cerveau, contexte, arguments.essais))
        print(mesurer_stabilite(client, cerveau, contexte, 8))
    for ouvriers in (1, 2, 4):
        print(mesurer_debit(client, cerveau, ouvriers, arguments.essais))


if __name__ == "__main__":
    main()
