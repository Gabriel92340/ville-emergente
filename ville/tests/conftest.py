import pytest

from ville.moteur.carte import Carte


def donnees_grille() -> dict:
    noeuds = [
        {"id": identifiant, "lat": 45.0 + ligne * 0.001, "lon": 4.0 + colonne * 0.001}
        for identifiant, (ligne, colonne) in {
            1: (1, 0),
            2: (1, 1),
            3: (1, 2),
            4: (0, 0),
            5: (0, 1),
            6: (0, 2),
        }.items()
    ]
    paires = [(1, 2), (2, 3), (4, 5), (5, 6), (1, 4), (2, 5), (3, 6)]
    aretes = []
    for origine, destination in paires:
        aretes.append({"origine": origine, "destination": destination, "longueur": 100.0})
        aretes.append({"origine": destination, "destination": origine, "longueur": 100.0})
    return {"noeuds": noeuds, "aretes": aretes}


@pytest.fixture
def carte_grille() -> Carte:
    return Carte(donnees_grille())
