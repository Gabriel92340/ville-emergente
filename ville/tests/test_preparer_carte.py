import networkx as nx
import pytest

from ville.moteur.carte import Carte
from ville.moteur.preparer_carte import convertir_graphe, telecharger


def petit_graphe() -> nx.MultiDiGraph:
    graphe = nx.MultiDiGraph()
    for noeud, (y, x) in {1: (45.0, 4.0), 2: (45.1, 4.1), 3: (45.2, 4.2), 9: (46.0, 5.0)}.items():
        graphe.add_node(noeud, y=y, x=x)
    graphe.add_edge(1, 2, length=10.12345)
    graphe.add_edge(2, 1, length=10.12345)
    graphe.add_edge(2, 3, length=20.0)
    graphe.add_edge(3, 2, length=20.0)
    graphe.add_edge(2, 3, length=25.0)
    graphe.add_edge(3, 3, length=5.0)
    graphe.add_edge(3, 9, length=30.0)
    return graphe


def test_garde_la_plus_grande_composante_fortement_connexe():
    donnees = convertir_graphe(petit_graphe())
    assert [noeud["id"] for noeud in donnees["noeuds"]] == [1, 2, 3]
    assert all(arete["destination"] != 9 for arete in donnees["aretes"])


def test_arrondit_les_longueurs():
    donnees = convertir_graphe(petit_graphe())
    assert {"origine": 1, "destination": 2, "longueur": 10.123} in donnees["aretes"]


def test_ignore_les_boucles():
    donnees = convertir_graphe(petit_graphe())
    assert all(arete["origine"] != arete["destination"] for arete in donnees["aretes"])


def test_resultat_exploitable_par_la_carte():
    carte = Carte(convertir_graphe(petit_graphe()))
    assert carte.est_fortement_connexe()
    assert carte.longueur(2, 3) == 20.0


def test_egalite_de_taille_departagee_par_le_plus_petit_identifiant():
    graphe = nx.MultiDiGraph()
    for noeud in (1, 2, 3, 4):
        graphe.add_node(noeud, y=45.0, x=4.0)
    for a, b in ((3, 4), (1, 2)):
        graphe.add_edge(a, b, length=1.0)
        graphe.add_edge(b, a, length=1.0)
    donnees = convertir_graphe(graphe)
    assert [noeud["id"] for noeud in donnees["noeuds"]] == [1, 2]


def test_longueur_nulle_refusee():
    graphe = nx.MultiDiGraph()
    graphe.add_node(1, y=45.0, x=4.0)
    graphe.add_node(2, y=45.0, x=4.0)
    graphe.add_edge(1, 2, length=0.0)
    graphe.add_edge(2, 1, length=0.0)
    with pytest.raises(ValueError):
        convertir_graphe(graphe)


@pytest.mark.reseau
def test_telechargement_reel():
    graphe = telecharger(45.7610, 4.8330, 200, "walk")
    assert Carte(convertir_graphe(graphe)).est_fortement_connexe()
