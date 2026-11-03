import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from ville.cerveau.client import Client, ClientOllama, DemandeModele, ErreurModele
from ville.cerveau.memoire import Memoire
from ville.cerveau.prompts import construire_prompt
from ville.cerveau.reponses import ReponseInvalide, analyser_plan, schema_plan
from ville.configuration import Configuration, ConfigurationCerveau
from ville.moteur.agent import Perception

LIEUX_EXEMPLE = {"domicile": 1, "travail": 2, "loisir_1": 3, "loisir_2": 4, "loisir_3": 5}


def demande_exemple(cerveau: ConfigurationCerveau, graine: int) -> DemandeModele:
    perception = Perception(
        tick=0,
        seconde_du_jour=8 * 3600,
        agent=0,
        noeud=1,
        etape="initial",
        budget_centimes=10000,
        domicile=1,
        travail=2,
        heure_travail_s=8 * 3600,
    )
    memoire = Memoire(cerveau.taille_memoire)
    for rang in range(cerveau.taille_memoire):
        memoire.retenir(f"07h{rang:02d} : attente pendant 1 min")
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


def mesurer_sequentiel(client: Client, cerveau: ConfigurationCerveau, essais: int) -> dict:
    latences, valides, erreurs = [], 0, 0
    for graine in range(essais):
        debut = time.perf_counter()
        try:
            texte = client.generer(demande_exemple(cerveau, graine))
            analyser_plan(texte, LIEUX_EXEMPLE, cerveau)
            valides += 1
        except ReponseInvalide:
            pass
        except ErreurModele:
            erreurs += 1
        latences.append(time.perf_counter() - debut)
    latences.sort()
    return {
        "essais": essais,
        "valides": valides,
        "erreurs": erreurs,
        "latence_mediane_s": latences[len(latences) // 2],
        "latence_max_s": latences[-1],
    }


def mesurer_stabilite(client: Client, cerveau: ConfigurationCerveau, essais: int) -> dict:
    demande = demande_exemple(cerveau, 1234)
    reponses = [client.generer(demande) for _ in range(essais)]
    autre = client.generer(replace(demande, graine=4321))
    return {
        "repetitions": essais,
        "reponses_distinctes": len(set(reponses)),
        "autre_graine_differe": autre != reponses[0],
    }


def mesurer_debit(client: Client, cerveau: ConfigurationCerveau, ouvriers: int, appels: int) -> dict:
    demandes = [demande_exemple(cerveau, graine) for graine in range(appels)]
    debut = time.perf_counter()
    with ThreadPoolExecutor(max_workers=ouvriers) as executeur:
        list(executeur.map(client.generer, demandes))
    duree = time.perf_counter() - debut
    return {"ouvriers": ouvriers, "appels": appels, "appels_par_seconde": appels / duree}


def main() -> None:
    analyseur = argparse.ArgumentParser(description="Mesurer le modèle local")
    analyseur.add_argument("--modele", default=ConfigurationCerveau.modele)
    analyseur.add_argument("--url-ollama", default="http://localhost:11434")
    analyseur.add_argument("--essais", type=int, default=20)
    arguments = analyseur.parse_args()
    cerveau = ConfigurationCerveau(modele=arguments.modele)
    client = ClientOllama(arguments.url_ollama)
    client.generer(demande_exemple(cerveau, 0))
    print(mesurer_sequentiel(client, cerveau, arguments.essais))
    print(mesurer_stabilite(client, cerveau, 5))
    for ouvriers in (1, 2, 4):
        print(mesurer_debit(client, cerveau, ouvriers, arguments.essais))


if __name__ == "__main__":
    main()
