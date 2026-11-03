import json
from typing import TextIO


class Journal:
    def __init__(self, sortie: TextIO):
        self._sortie = sortie

    def ecrire(self, evenement: dict) -> None:
        ligne = json.dumps(
            evenement,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        self._sortie.write(ligne + "\n")
