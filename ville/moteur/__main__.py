import argparse
import sys
import time
from pathlib import Path

from ville.configuration import Configuration
from ville.donnees.journal import Journal
from ville.moteur.carte import Carte
from ville.moteur.simulation import Simulation

CARTE_PAR_DEFAUT = Path(__file__).resolve().parent.parent / "cartes" / "lyon_presquile.json"


def main() -> int:
    analyseur = argparse.ArgumentParser(description="Lancer la simulation sans LLM")
    analyseur.add_argument("--graine", type=int, default=42)
    analyseur.add_argument("--heures", type=float, default=24.0)
    analyseur.add_argument("--agents", type=int, default=100)
    analyseur.add_argument("--duree-tick", type=int, default=10)
    analyseur.add_argument("--carte", type=Path, default=CARTE_PAR_DEFAUT)
    analyseur.add_argument("--journal", type=Path)
    arguments = analyseur.parse_args()

    if not arguments.carte.exists():
        print(
            f"carte introuvable : {arguments.carte} (la produire avec ville.moteur.preparer_carte)",
            file=sys.stderr,
        )
        return 2

    configuration = Configuration(
        graine=arguments.graine,
        nb_agents=arguments.agents,
        duree_tick_s=arguments.duree_tick,
    )
    carte = Carte.charger(arguments.carte)
    chemin_journal = arguments.journal or Path("sorties") / f"journal_graine_{arguments.graine}.jsonl"
    chemin_journal.parent.mkdir(parents=True, exist_ok=True)
    nb_ticks = int(arguments.heures * 3600 / configuration.duree_tick_s)

    debut = time.perf_counter()
    with open(chemin_journal, "w", encoding="utf-8", newline="\n") as sortie:
        simulation = Simulation(configuration, carte, Journal(sortie))
        for _ in range(nb_ticks):
            simulation.avancer()
    duree = time.perf_counter() - debut

    distance_km = sum(agent.distance_parcourue for agent in simulation.agents) / 1000
    print(f"carte : {len(carte.noeuds)} nœuds, empreinte {carte.empreinte[:12]}")
    print(f"agents : {configuration.nb_agents}, ticks : {nb_ticks}, graine : {configuration.graine}")
    print(f"décisions : {simulation.nb_decisions}, distance parcourue : {distance_km:.1f} km")
    print(f"journal : {chemin_journal}")
    print(f"temps de calcul : {duree:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
