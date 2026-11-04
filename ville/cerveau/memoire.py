from collections import deque


class Memoire:
    def __init__(self, taille: int):
        self._souvenirs: deque[str] = deque(maxlen=taille)
        self._faits: dict[str, int] = {}

    def retenir(self, souvenir: str) -> None:
        self._souvenirs.append(souvenir)

    def compter(self, fait: str) -> None:
        self._faits[fait] = self._faits.get(fait, 0) + 1

    @property
    def souvenirs(self) -> list[str]:
        return list(self._souvenirs)

    @property
    def faits(self) -> list[tuple[str, int]]:
        return sorted(self._faits.items())
