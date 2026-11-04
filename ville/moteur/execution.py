import threading
from dataclasses import dataclass

from ville.moteur.simulation import Simulation


@dataclass(frozen=True)
class EtatAgent:
    identifiant: int
    latitude: float
    longitude: float
    etape: str
    budget_centimes: int


@dataclass(frozen=True)
class Instantane:
    tick: int
    secondes: int
    agents: tuple[EtatAgent, ...]


def photographier(simulation: Simulation) -> Instantane:
    agents = []
    for agent in simulation.agents:
        latitude, longitude = agent.position(simulation.carte)
        agents.append(
            EtatAgent(agent.identifiant, latitude, longitude, agent.etape, agent.budget_centimes)
        )
    return Instantane(simulation.horloge.tick, simulation.horloge.secondes, tuple(agents))


class Execution:
    def __init__(self, simulation: Simulation, nb_ticks: int):
        self._simulation = simulation
        self._nb_ticks = nb_ticks
        self._arret = threading.Event()
        self._instantane = photographier(simulation)
        self.erreur: BaseException | None = None
        self._fil = threading.Thread(target=self._boucler, name="simulation", daemon=True)

    def demarrer(self) -> None:
        self._fil.start()

    def _boucler(self) -> None:
        try:
            for _ in range(self._nb_ticks):
                if self._arret.is_set():
                    return
                self._simulation.avancer()
                self._instantane = photographier(self._simulation)
        except BaseException as erreur:
            self.erreur = erreur

    def instantane(self) -> Instantane:
        return self._instantane

    def arreter(self) -> None:
        self._arret.set()

    def est_active(self) -> bool:
        return self._fil.is_alive()

    def attendre(self, delai_s: float | None = None) -> None:
        self._fil.join(delai_s)
        if self.erreur is not None:
            raise self.erreur
