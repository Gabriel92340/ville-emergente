import json
import threading
import time
from typing import TextIO


class Mesures:
    def __init__(self, sortie: TextIO | None = None):
        self._sortie = sortie
        self._verrou = threading.Lock()
        self.latences_s: list[float] = []
        self.attentes_s: list[float] = []
        self.replis = 0

    def chrono(self) -> float:
        return time.perf_counter()

    def noter_latence(self, agent: int, tick: int, duree_s: float) -> None:
        with self._verrou:
            self.latences_s.append(duree_s)
            self._ecrire({"type": "latence", "agent": agent, "tick": tick, "duree_s": duree_s})

    def noter_attente(self, agent: int, tick: int, duree_s: float) -> None:
        with self._verrou:
            self.attentes_s.append(duree_s)
            self._ecrire({"type": "attente", "agent": agent, "tick": tick, "duree_s": duree_s})

    def noter_repli(self) -> None:
        with self._verrou:
            self.replis += 1

    def _ecrire(self, ligne: dict) -> None:
        if self._sortie is not None:
            self._sortie.write(json.dumps(ligne, sort_keys=True) + "\n")
