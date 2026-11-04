from dataclasses import asdict, dataclass, field
from random import Random
from typing import Protocol

from ville.moteur.carte import Carte

ETAPE_INITIALE = "initial"
ATTENTE = "attente"
TRAVAIL = "travail"
LOISIR = "loisir"
DOMICILE = "domicile"
PREFIXE_ARRIVEE = "arrivee_"


@dataclass(frozen=True)
class Aller:
    destination: int
    motif: str


@dataclass(frozen=True)
class Activite:
    nature: str
    duree_s: int


Intention = Aller | Activite


def intention_en_dict(intention: Intention) -> dict:
    if not isinstance(intention, (Aller, Activite)):
        raise ValueError(f"intention inconnue : {intention!r}")
    return {"type": type(intention).__name__, **asdict(intention)}


@dataclass(frozen=True)
class Perception:
    tick: int
    seconde_du_jour: int
    agent: int
    noeud: int
    etape: str
    budget_centimes: int
    domicile: int
    travail: int
    heure_travail_s: int


class Decideur(Protocol):
    def decider(self, perception: Perception, flux: Random) -> Intention: ...


class Cerveau(Protocol):
    def description(self) -> dict: ...

    def demarrer(self, simulation) -> None: ...

    def tour(self, tick: int) -> None: ...

    def decider(self, perception: Perception, flux: Random) -> tuple[Intention, str]: ...

    def observer(self, evenement: dict) -> None: ...


@dataclass
class Agent:
    identifiant: int
    domicile: int
    travail: int
    vitesse_m_s: float
    heure_travail_s: int
    budget_centimes: int
    noeud: int
    etape: str = ETAPE_INITIALE
    chemin: list[int] = field(default_factory=list)
    distance_sur_arete: float = 0.0
    motif: str | None = None
    activite: str | None = None
    fin_activite_tick: int | None = None
    duree_activite_s: int = 0
    distance_parcourue: float = 0.0

    @property
    def est_en_trajet(self) -> bool:
        return self.motif is not None

    @property
    def est_libre(self) -> bool:
        return self.motif is None and self.activite is None

    def commencer_trajet(self, chemin: list[int], motif: str) -> None:
        if chemin[0] != self.noeud:
            raise ValueError(f"le chemin de l'agent {self.identifiant} ne part pas de sa position")
        self.chemin = chemin[1:]
        self.distance_sur_arete = 0.0
        self.motif = motif

    def commencer_activite(self, nature: str, duree_s: int, fin_tick: int) -> None:
        self.activite = nature
        self.duree_activite_s = duree_s
        self.fin_activite_tick = fin_tick

    def terminer_activite(self) -> None:
        self.etape = self.activite
        self.activite = None
        self.fin_activite_tick = None
        self.duree_activite_s = 0

    def avancer(self, distance: float, carte: Carte) -> bool:
        restante = distance
        while self.chemin:
            prochain = self.chemin[0]
            reste_arete = carte.longueur(self.noeud, prochain) - self.distance_sur_arete
            if restante < reste_arete:
                self.distance_sur_arete += restante
                self.distance_parcourue += restante
                return False
            restante -= reste_arete
            self.distance_parcourue += reste_arete
            self.noeud = prochain
            self.chemin.pop(0)
            self.distance_sur_arete = 0.0
        self.etape = PREFIXE_ARRIVEE + self.motif
        self.motif = None
        return True

    def position(self, carte: Carte) -> tuple[float, float]:
        if self.chemin:
            return carte.interpoler(self.noeud, self.chemin[0], self.distance_sur_arete)
        return carte.coordonnees(self.noeud)
