import hashlib
import json
from pathlib import Path

import networkx as nx


class CheminIntrouvable(Exception):
    pass


class Carte:
    def __init__(self, donnees: dict):
        self._donnees = self._normaliser(donnees)
        self._graphe = nx.DiGraph()
        self._coordonnees: dict[int, tuple[float, float]] = {}
        self._chemins: dict[tuple[int, int], list[int]] = {}
        for noeud in self._donnees["noeuds"]:
            self._graphe.add_node(noeud["id"])
            self._coordonnees[noeud["id"]] = (noeud["lat"], noeud["lon"])
        for arete in self._donnees["aretes"]:
            self._graphe.add_edge(
                arete["origine"], arete["destination"], longueur=arete["longueur"]
            )
        self.noeuds: list[int] = [noeud["id"] for noeud in self._donnees["noeuds"]]

    @classmethod
    def charger(cls, chemin: str | Path) -> "Carte":
        with open(chemin, encoding="utf-8") as fichier:
            return cls(json.load(fichier))

    @staticmethod
    def _normaliser(donnees: dict) -> dict:
        noeuds = sorted(donnees["noeuds"], key=lambda noeud: noeud["id"])
        identifiants = {noeud["id"] for noeud in noeuds}
        if len(identifiants) != len(noeuds):
            raise ValueError("identifiant de nœud en double dans la carte")
        plus_courtes: dict[tuple[int, int], float] = {}
        for arete in donnees["aretes"]:
            origine, destination, longueur = (
                arete["origine"],
                arete["destination"],
                arete["longueur"],
            )
            if origine not in identifiants or destination not in identifiants:
                raise ValueError(f"arête vers un nœud inconnu : {origine} -> {destination}")
            if longueur <= 0:
                raise ValueError(f"longueur invalide sur l'arête {origine} -> {destination}")
            if origine == destination:
                continue
            cle = (origine, destination)
            if cle not in plus_courtes or longueur < plus_courtes[cle]:
                plus_courtes[cle] = longueur
        aretes = [
            {"origine": origine, "destination": destination, "longueur": longueur}
            for (origine, destination), longueur in sorted(plus_courtes.items())
        ]
        return {"noeuds": noeuds, "aretes": aretes}

    @property
    def empreinte(self) -> str:
        return hashlib.sha256(self.serialiser().encode("utf-8")).hexdigest()

    def serialiser(self) -> str:
        return json.dumps(
            self._donnees, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def est_fortement_connexe(self) -> bool:
        return nx.is_strongly_connected(self._graphe)

    def contient_arete(self, origine: int, destination: int) -> bool:
        return self._graphe.has_edge(origine, destination)

    def longueur(self, origine: int, destination: int) -> float:
        return self._graphe[origine][destination]["longueur"]

    def plus_court_chemin(self, origine: int, destination: int) -> list[int]:
        cle = (origine, destination)
        if cle not in self._chemins:
            try:
                self._chemins[cle] = nx.dijkstra_path(
                    self._graphe, origine, destination, weight="longueur"
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound) as erreur:
                raise CheminIntrouvable(
                    f"aucun chemin de {origine} vers {destination}"
                ) from erreur
        return list(self._chemins[cle])

    def coordonnees(self, noeud: int) -> tuple[float, float]:
        return self._coordonnees[noeud]

    def interpoler(self, origine: int, destination: int, distance: float) -> tuple[float, float]:
        fraction = distance / self.longueur(origine, destination)
        lat_a, lon_a = self._coordonnees[origine]
        lat_b, lon_b = self._coordonnees[destination]
        return (lat_a + (lat_b - lat_a) * fraction, lon_a + (lon_b - lon_a) * fraction)
