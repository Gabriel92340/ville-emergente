import io
import json

import pytest

from ville.configuration import Configuration
from ville.donnees.journal import Journal
from ville.moteur.simulation import Simulation


def lignes_d_une_simulation(carte, ticks=2000):
    sortie = io.StringIO()
    simulation = Simulation(
        Configuration(nb_agents=3, heure_depart_s=8 * 3600 - 3600), carte, Journal(sortie)
    )
    for _ in range(ticks):
        simulation.avancer()
    return [json.loads(ligne) for ligne in sortie.getvalue().splitlines()], simulation


def test_ecrit_une_ligne_json_canonique():
    sortie = io.StringIO()
    Journal(sortie).ecrire({"b": 1, "a": "é"})
    assert sortie.getvalue() == '{"a":"é","b":1}\n'


def test_refuse_les_valeurs_non_finies():
    with pytest.raises(ValueError):
        Journal(io.StringIO()).ecrire({"a": float("nan")})


def test_l_entete_decrit_l_execution(carte_grille):
    lignes, simulation = lignes_d_une_simulation(carte_grille, ticks=0)
    entete = lignes[0]
    assert entete["type"] == "entete"
    assert entete["graine"] == 42
    assert entete["configuration"]["nb_agents"] == 3
    assert entete["empreinte_carte"] == carte_grille.empreinte
    assert entete["python"]


def test_une_ligne_par_decision_avec_tous_ses_champs(carte_grille):
    lignes, simulation = lignes_d_une_simulation(carte_grille)
    decisions = [ligne for ligne in lignes if ligne["type"] == "decision"]
    assert len(decisions) == simulation.nb_decisions > 0
    for decision in decisions:
        assert set(decision) == {
            "type",
            "tick",
            "agent",
            "graine",
            "flux",
            "contexte",
            "intention",
            "reponse_brute",
        }
        assert decision["graine"] == 42
        assert decision["flux"] == f"agents/{decision['agent']}/decision"
        assert decision["reponse_brute"] is None


def test_arrivees_journalisees(carte_grille):
    lignes, _ = lignes_d_une_simulation(carte_grille)
    arrivees = [ligne for ligne in lignes if ligne["type"] == "arrivee"]
    assert arrivees
    assert all(ligne["etape"].startswith("arrivee_") for ligne in arrivees)


def test_aucun_horodatage_reel(carte_grille):
    lignes, _ = lignes_d_une_simulation(carte_grille)
    for ligne in lignes:
        assert not {"date", "horodatage", "timestamp", "maintenant"} & set(ligne)
