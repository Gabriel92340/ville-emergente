from pathlib import Path

import pytest

import ville
from ville.configuration import Configuration
from ville.moteur.carte import Carte
from ville.moteur.simulation import Simulation

CHEMIN_EXTRAIT = Path(ville.__file__).parent / "cartes" / "lyon_presquile.json"

pytestmark = pytest.mark.skipif(
    not CHEMIN_EXTRAIT.exists(), reason="extrait figé absent : lancer ville.moteur.preparer_carte"
)


class JournalMuet:
    def ecrire(self, evenement):
        pass


@pytest.fixture(scope="module")
def carte_reelle():
    return Carte.charger(CHEMIN_EXTRAIT)


def test_l_extrait_est_fortement_connexe(carte_reelle):
    assert carte_reelle.est_fortement_connexe()


def test_l_extrait_a_une_taille_de_quartier(carte_reelle):
    assert len(carte_reelle.noeuds) > 100


def test_l_extrait_est_sous_forme_canonique(carte_reelle):
    assert CHEMIN_EXTRAIT.read_text(encoding="utf-8") == carte_reelle.serialiser()


def test_cent_agents_circulent_sur_la_carte_reelle(carte_reelle):
    simulation = Simulation(Configuration(nb_agents=100), carte_reelle, JournalMuet())
    for _ in range(4 * 360):
        simulation.avancer()
    assert sum(agent.distance_parcourue for agent in simulation.agents) > 0
    for agent in simulation.agents:
        assert agent.noeud in carte_reelle.noeuds
