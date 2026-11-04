import argparse
import sys
import time
from pathlib import Path

from ville.cerveau.client import ClientOllama
from ville.cerveau.decideur import CerveauLLM
from ville.cerveau.rejeu import (
    ClientRejeu,
    RejeuDivergent,
    configurations_du_journal,
    lire_entete,
)
from ville.configuration import Configuration, ConfigurationCerveau
from ville.donnees.journal import Journal
from ville.donnees.mesures import Mesures
from ville.moteur.carte import Carte
from ville.moteur.execution import Execution
from ville.moteur.simulation import Simulation

CARTE_PAR_DEFAUT = Path(__file__).resolve().parent.parent / "cartes" / "lyon_presquile.json"


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(description="Lancer la simulation")
    analyseur.add_argument("--graine", type=int, default=42)
    analyseur.add_argument("--heures", type=float, default=24.0)
    analyseur.add_argument("--agents", type=int, default=100)
    analyseur.add_argument("--duree-tick", type=int, default=10)
    analyseur.add_argument("--heure-depart", type=float, default=6.0)
    analyseur.add_argument("--carte", type=Path, default=CARTE_PAR_DEFAUT)
    analyseur.add_argument("--journal", type=Path)
    analyseur.add_argument("--cerveau", action="store_true")
    analyseur.add_argument("--modele", default=ConfigurationCerveau.modele)
    analyseur.add_argument("--quota", type=int, default=ConfigurationCerveau.quota_agents)
    analyseur.add_argument("--periode", type=int, default=ConfigurationCerveau.periode_ticks)
    analyseur.add_argument("--delai", type=int, default=ConfigurationCerveau.delai_ticks)
    analyseur.add_argument("--ouvriers", type=int, default=1)
    analyseur.add_argument("--url-ollama", default="http://127.0.0.1:11434")
    analyseur.add_argument("--delai-max-appel", type=float, default=120.0)
    analyseur.add_argument("--rejeu", type=Path)
    analyseur.add_argument("--mesures", type=Path)
    return analyseur.parse_args()


def preparer_configurations(arguments, carte: Carte):
    if arguments.rejeu is not None:
        entete = lire_entete(arguments.rejeu)
        if entete["empreinte_carte"] != carte.empreinte:
            raise RejeuDivergent("la carte diffère de celle du journal")
        configuration, cerveau = configurations_du_journal(entete)
        return configuration, cerveau, ClientRejeu(arguments.rejeu)
    configuration = Configuration(
        graine=arguments.graine,
        nb_agents=arguments.agents,
        duree_tick_s=arguments.duree_tick,
        heure_depart_s=int(arguments.heure_depart * 3600),
    )
    if not arguments.cerveau:
        return configuration, None, None
    cerveau = ConfigurationCerveau(
        modele=arguments.modele,
        quota_agents=arguments.quota,
        periode_ticks=arguments.periode,
        delai_ticks=arguments.delai,
    )
    return configuration, cerveau, ClientOllama(arguments.url_ollama, arguments.delai_max_appel)


def afficher_mesures(cerveau: CerveauLLM, mesures: Mesures) -> None:
    latences = sorted(mesures.latences_s)
    print(f"réflexions : {cerveau.nb_reflexions}, replis : {mesures.replis}")
    if latences:
        mediane = latences[len(latences) // 2]
        print(f"latence du modèle : médiane {mediane:.2f} s, maximum {latences[-1]:.2f} s")
    print(f"attente de la simulation : {sum(mesures.attentes_s):.2f} s")


def surveiller(execution: Execution) -> dict:
    lectures, lecture_max_s, gel_max_s = 0, 0.0, 0.0
    dernier_tick, debut_tick = None, time.perf_counter()
    while execution.est_active():
        debut = time.perf_counter()
        tick = execution.instantane().tick
        fin = time.perf_counter()
        lectures += 1
        lecture_max_s = max(lecture_max_s, fin - debut)
        if tick != dernier_tick:
            dernier_tick, debut_tick = tick, fin
        gel_max_s = max(gel_max_s, fin - debut_tick)
        time.sleep(0.1)
    return {"lectures": lectures, "lecture_max_ms": lecture_max_s * 1000, "gel_max_s": gel_max_s}


def executer(arguments) -> int:
    carte = Carte.charger(arguments.carte)
    configuration, cerveau_config, client = preparer_configurations(arguments, carte)
    graine = configuration.graine
    chemin_journal = arguments.journal or Path("sorties") / f"journal_graine_{graine}.jsonl"
    chemin_journal.parent.mkdir(parents=True, exist_ok=True)
    nb_ticks = int(arguments.heures * 3600 / configuration.duree_tick_s)
    sortie_mesures = None
    if arguments.mesures is not None:
        arguments.mesures.parent.mkdir(parents=True, exist_ok=True)
        sortie_mesures = open(arguments.mesures, "w", encoding="utf-8", newline="\n")
    mesures = Mesures(sortie_mesures)
    cerveau = None
    if cerveau_config is not None:
        cerveau = CerveauLLM(cerveau_config, client, arguments.ouvriers, mesures)

    debut = time.perf_counter()
    try:
        with open(chemin_journal, "w", encoding="utf-8", newline="\n") as sortie:
            simulation = Simulation(configuration, carte, Journal(sortie), cerveau=cerveau)
            execution = Execution(simulation, nb_ticks)
            execution.demarrer()
            fluidite = surveiller(execution) if cerveau is not None else None
            execution.attendre()
    finally:
        if cerveau is not None:
            cerveau.fermer()
        if sortie_mesures is not None:
            sortie_mesures.close()
    duree = time.perf_counter() - debut

    distance_km = sum(agent.distance_parcourue for agent in simulation.agents) / 1000
    print(f"carte : {len(carte.noeuds)} nœuds, empreinte {carte.empreinte[:12]}")
    print(f"agents : {configuration.nb_agents}, ticks : {nb_ticks}, graine : {graine}")
    print(f"décisions : {simulation.nb_decisions}, distance parcourue : {distance_km:.1f} km")
    if cerveau is not None:
        afficher_mesures(cerveau, mesures)
        print(
            f"lecteur à 10 Hz : {fluidite['lectures']} lectures, "
            f"lecture la plus lente {fluidite['lecture_max_ms']:.2f} ms, "
            f"plus longue durée sans nouveau tick {fluidite['gel_max_s']:.2f} s"
        )
    print(f"journal : {chemin_journal}")
    print(f"temps de calcul : {duree:.2f} s")
    return 0


def main() -> int:
    arguments = analyser_arguments()
    if not arguments.carte.exists():
        print(
            f"carte introuvable : {arguments.carte} (la produire avec ville.moteur.preparer_carte)",
            file=sys.stderr,
        )
        return 2
    try:
        return executer(arguments)
    except RejeuDivergent as erreur:
        print(f"rejeu impossible : {erreur}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
