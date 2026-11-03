from random import Random


class Ordonnanceur:
    def __init__(self, quota: int, periode_ticks: int, flux: Random):
        if quota < 0 or periode_ticks <= 0:
            raise ValueError("quota ou période de réflexion invalide")
        self._quota = quota
        self._periode_ticks = periode_ticks
        self._flux = flux

    def est_tour_de_reflexion(self, tick: int) -> bool:
        return tick % self._periode_ticks == 0

    def tirer(self, candidats: list[int]) -> list[int]:
        restants = sorted(candidats)
        nombre = min(self._quota, len(restants))
        for position in range(nombre):
            autre = position + int(self._flux.random() * (len(restants) - position))
            restants[position], restants[autre] = restants[autre], restants[position]
        return sorted(restants[:nombre])
