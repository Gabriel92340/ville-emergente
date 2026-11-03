import hashlib
import random


class SourceAlea:
    def __init__(self, graine: int):
        self.graine = graine
        self._flux: dict[str, random.Random] = {}

    def flux(self, nom: str) -> random.Random:
        if nom not in self._flux:
            self._flux[nom] = random.Random(self._deriver(nom))
        return self._flux[nom]

    def _deriver(self, nom: str) -> int:
        condensat = hashlib.sha256(f"{self.graine}/{nom}".encode("utf-8")).digest()
        return int.from_bytes(condensat, "big")
