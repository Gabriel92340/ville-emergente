SCORE_MIN = -100
SCORE_MAX = 100


class Relations:
    def __init__(self):
        self._scores: dict[tuple[int, int], int] = {}

    @staticmethod
    def _cle(a: int, b: int) -> tuple[int, int]:
        if a == b:
            raise ValueError(f"un agent n'a pas de relation avec lui-même : {a}")
        return (a, b) if a < b else (b, a)

    def score(self, a: int, b: int) -> int:
        return self._scores.get(self._cle(a, b), 0)

    def modifier(self, a: int, b: int, variation: int) -> int:
        cle = self._cle(a, b)
        nouveau = max(SCORE_MIN, min(SCORE_MAX, self._scores.get(cle, 0) + variation))
        self._scores[cle] = nouveau
        return nouveau

    def meilleures(self, agent: int, nombre: int) -> list[tuple[int, int]]:
        connaissances = []
        for (a, b), score in self._scores.items():
            if agent in (a, b):
                connaissances.append((b if a == agent else a, score))
        return sorted(connaissances, key=lambda paire: (-paire[1], paire[0]))[:nombre]
