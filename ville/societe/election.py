from collections import Counter
from dataclasses import dataclass
from random import Random
from typing import Callable

from ville.societe.relations import Relations

PREFIXE_CANDIDAT = "habitant_"


@dataclass(frozen=True)
class Candidat:
    agent: int
    taux_impot_pourcent: int

    @property
    def nom(self) -> str:
        return f"{PREFIXE_CANDIDAT}{self.agent}"


class Election:
    def __init__(self, candidats: list[Candidat], tick_vote: int):
        if len(candidats) < 2:
            raise ValueError("une élection demande au moins deux candidats")
        if len({candidat.agent for candidat in candidats}) != len(candidats):
            raise ValueError("candidat en double dans l'élection")
        self.candidats = sorted(candidats, key=lambda candidat: candidat.agent)
        self.tick_vote = tick_vote
        self._votes_exprimes: dict[int, int] = {}

    def noms(self) -> list[str]:
        return [candidat.nom for candidat in self.candidats]

    def enregistrer_vote(self, votant: int, nom: str) -> None:
        for candidat in self.candidats:
            if candidat.nom == nom:
                self._votes_exprimes[votant] = candidat.agent
                return
        raise ValueError(f"candidat inconnu : {nom}")

    def _vote_selon_les_regles(self, votant: int, relations: Relations, flux: Random) -> int:
        for candidat in self.candidats:
            if candidat.agent == votant:
                return votant
        meilleur = max(relations.score(votant, candidat.agent) for candidat in self.candidats)
        favoris = [
            candidat.agent
            for candidat in self.candidats
            if relations.score(votant, candidat.agent) == meilleur
        ]
        return favoris[int(flux.random() * len(favoris))]

    def depouiller(
        self,
        votants: list[int],
        relations: Relations,
        flux_de: Callable[[int], Random],
        flux_egalite: Random,
    ) -> tuple[Candidat, dict]:
        bulletins: Counter[int] = Counter()
        par_le_modele = 0
        for votant in sorted(votants):
            if votant in self._votes_exprimes:
                bulletins[self._votes_exprimes[votant]] += 1
                par_le_modele += 1
            else:
                bulletins[self._vote_selon_les_regles(votant, relations, flux_de(votant))] += 1
        maximum = max(bulletins.values())
        premiers = [c for c in self.candidats if bulletins[c.agent] == maximum]
        elu = premiers[int(flux_egalite.random() * len(premiers))]
        return elu, {
            "type": "election_resultat",
            "bulletins": {str(c.agent): bulletins[c.agent] for c in self.candidats},
            "votes_du_modele": par_le_modele,
            "elu": elu.agent,
            "taux_impot_pourcent": elu.taux_impot_pourcent,
            "egalite": len(premiers) > 1,
        }
