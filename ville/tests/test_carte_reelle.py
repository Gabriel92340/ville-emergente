import os
import subprocess
import sys
from pathlib import Path

import pytest

import ville
from ville.configuration import Configuration
from ville.moteur.carte import Carte
from ville.moteur.simulation import Simulation

CHEMIN_EXTRAIT = Path(ville.__file__).parent / "cartes" / "lyon_presquile.json"
EMPREINTE_EXTRAIT = "b2bb2d1f66fbef211dd3c12fe6fc6df058554007e1fae259bc1aff7a67a3b2a6"
NB_NOEUDS_EXTRAIT = 4230


class JournalMuet:
    def ecrire(self, evenement):
        pass


@pytest.fixture(scope="module")
def carte_reelle():
    return Carte.charger(CHEMIN_EXTRAIT)


def test_l_empreinte_de_l_extrait_est_celle_attendue(carte_reelle):
    assert carte_reelle.empreinte == EMPREINTE_EXTRAIT


def test_l_extrait_a_le_nombre_de_noeuds_attendu(carte_reelle):
    assert len(carte_reelle.noeuds) == NB_NOEUDS_EXTRAIT


def test_l_extrait_est_fortement_connexe(carte_reelle):
    assert carte_reelle.est_fortement_connexe()


def test_l_extrait_est_sous_forme_canonique(carte_reelle):
    assert CHEMIN_EXTRAIT.read_text(encoding="utf-8") == carte_reelle.serialiser()


def test_cent_agents_circulent_sur_la_carte_reelle(carte_reelle):
    simulation = Simulation(Configuration(nb_agents=100), carte_reelle, JournalMuet())
    for _ in range(4 * 360):
        simulation.avancer()
    assert sum(agent.distance_parcourue for agent in simulation.agents) > 0
    for agent in simulation.agents:
        assert agent.noeud in carte_reelle.noeuds
        if agent.chemin:
            assert carte_reelle.contient_arete(agent.noeud, agent.chemin[0])


def executer(journal: Path, graine: int, hash_seed: str) -> bytes:
    resultat = subprocess.run(
        [
            sys.executable,
            "-m",
            "ville.moteur",
            "--graine",
            str(graine),
            "--heures",
            "24",
            "--journal",
            str(journal),
        ],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        capture_output=True,
        text=True,
    )
    assert resultat.returncode == 0, resultat.stderr
    return journal.read_bytes()


def test_reproductible_a_l_octet_sur_la_carte_reelle(tmp_path):
    premier = executer(tmp_path / "a.jsonl", 42, "1")
    second = executer(tmp_path / "b.jsonl", 42, "98765")
    autre_graine = executer(tmp_path / "c.jsonl", 43, "1")
    assert premier == second
    assert premier != autre_graine
