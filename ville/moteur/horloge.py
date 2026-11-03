from dataclasses import dataclass

SECONDES_PAR_JOUR = 86400


@dataclass
class Horloge:
    duree_tick_s: int = 10
    heure_depart_s: int = 0
    tick: int = 0

    def __post_init__(self):
        if not isinstance(self.duree_tick_s, int) or self.duree_tick_s <= 0:
            raise ValueError("la durée d'un tick doit être un entier strictement positif")

    def avancer(self) -> None:
        self.tick += 1

    @property
    def secondes(self) -> int:
        return self.heure_depart_s + self.tick * self.duree_tick_s

    @property
    def jour(self) -> int:
        return self.secondes // SECONDES_PAR_JOUR

    @property
    def seconde_du_jour(self) -> int:
        return self.secondes % SECONDES_PAR_JOUR

    def ticks_pour(self, secondes: int) -> int:
        return -(-secondes // self.duree_tick_s)
