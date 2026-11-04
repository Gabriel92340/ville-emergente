from dataclasses import dataclass, field
from random import Random
from typing import Callable


@dataclass
class Rumeur:
    identifiant: int
    contenu: str
    source: int
    tick: int
    apprise_par: dict[int, int] = field(default_factory=dict)


class Rumeurs:
    def __init__(self, probabilite_transmission: float):
        self._probabilite = probabilite_transmission
        self.rumeurs: list[Rumeur] = []

    def injecter(self, contenu: str, source: int, tick: int) -> dict:
        rumeur = Rumeur(len(self.rumeurs), contenu, source, tick, {source: tick})
        self.rumeurs.append(rumeur)
        return {
            "type": "rumeur_injectee",
            "rumeur": rumeur.identifiant,
            "contenu": contenu,
            "source": source,
        }

    def connues_par(self, agent: int) -> list[Rumeur]:
        return [rumeur for rumeur in self.rumeurs if agent in rumeur.apprise_par]

    def transmettre(
        self,
        a: int,
        b: int,
        tick: int,
        volonte: Callable[[int], bool | None],
        flux_de: Callable[[int], Random],
    ) -> list[dict]:
        evenements = []
        for rumeur in self.rumeurs:
            if (a in rumeur.apprise_par) == (b in rumeur.apprise_par):
                continue
            conteur, auditeur = (a, b) if a in rumeur.apprise_par else (b, a)
            choix = volonte(conteur)
            if choix is False:
                continue
            if choix is None and flux_de(rumeur.identifiant).random() >= self._probabilite:
                continue
            rumeur.apprise_par[auditeur] = tick
            evenements.append(
                {
                    "type": "rumeur_transmise",
                    "rumeur": rumeur.identifiant,
                    "de": conteur,
                    "a": auditeur,
                    "decidee_par_le_modele": choix is True,
                }
            )
        return evenements
