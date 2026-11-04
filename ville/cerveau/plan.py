from collections import deque
from dataclasses import dataclass

from ville.moteur.agent import DOMICILE, LOISIR, TRAVAIL, Activite, Aller, Intention, Perception

LIEU_DOMICILE = "domicile"
LIEU_TRAVAIL = "travail"


@dataclass(frozen=True)
class EtapePlan:
    lieu: str
    activite: str
    duree_minutes: int


def _motif(lieu: str) -> str:
    if lieu == LIEU_DOMICILE:
        return DOMICILE
    if lieu == LIEU_TRAVAIL:
        return TRAVAIL
    return LOISIR


class PlanJour:
    def __init__(self, etapes: list[EtapePlan], lieux: dict[str, int]):
        self._etapes = deque(etapes)
        self._lieux = lieux

    def prochaine_intention(self, perception: Perception, prix_loisir: int) -> Intention | None:
        while self._etapes:
            etape = self._etapes[0]
            noeud = self._lieux[etape.lieu]
            if perception.noeud != noeud:
                return Aller(noeud, _motif(etape.lieu))
            self._etapes.popleft()
            if etape.activite == LOISIR and perception.budget_centimes < prix_loisir:
                continue
            return Activite(etape.activite, etape.duree_minutes * 60)
        return None
