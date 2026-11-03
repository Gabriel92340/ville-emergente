import argparse
from pathlib import Path

import networkx as nx

from ville.moteur.carte import Carte

DECIMALES_COORDONNEES = 7
DECIMALES_LONGUEUR = 3


def convertir_graphe(graphe: nx.MultiDiGraph) -> dict:
    composantes = nx.strongly_connected_components(graphe)
    retenue = max(composantes, key=lambda composante: (len(composante), -min(composante)))
    noeuds = [
        {
            "id": int(noeud),
            "lat": round(float(graphe.nodes[noeud]["y"]), DECIMALES_COORDONNEES),
            "lon": round(float(graphe.nodes[noeud]["x"]), DECIMALES_COORDONNEES),
        }
        for noeud in sorted(retenue)
    ]
    aretes = []
    for origine, destination, attributs in graphe.edges(data=True):
        if origine not in retenue or destination not in retenue or origine == destination:
            continue
        longueur = round(float(attributs["length"]), DECIMALES_LONGUEUR)
        if longueur <= 0:
            raise ValueError(f"longueur nulle sur l'arête {origine} -> {destination}")
        aretes.append(
            {"origine": int(origine), "destination": int(destination), "longueur": longueur}
        )
    return {"noeuds": noeuds, "aretes": aretes}


def telecharger(latitude: float, longitude: float, rayon_m: int, reseau: str) -> nx.MultiDiGraph:
    import osmnx

    return osmnx.graph_from_point(
        (latitude, longitude), dist=rayon_m, network_type=reseau, simplify=True
    )


def main() -> None:
    analyseur = argparse.ArgumentParser(description="Figer un extrait OpenStreetMap")
    analyseur.add_argument("--latitude", type=float, required=True)
    analyseur.add_argument("--longitude", type=float, required=True)
    analyseur.add_argument("--rayon", type=int, default=1000)
    analyseur.add_argument("--reseau", default="walk")
    analyseur.add_argument("--sortie", type=Path, required=True)
    arguments = analyseur.parse_args()

    graphe = telecharger(arguments.latitude, arguments.longitude, arguments.rayon, arguments.reseau)
    carte = Carte(convertir_graphe(graphe))
    arguments.sortie.parent.mkdir(parents=True, exist_ok=True)
    arguments.sortie.write_text(carte.serialiser(), encoding="utf-8", newline="\n")
    print(f"{len(carte.noeuds)} nœuds écrits dans {arguments.sortie}, empreinte {carte.empreinte}")


if __name__ == "__main__":
    main()
