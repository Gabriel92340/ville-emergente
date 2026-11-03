import io
from random import Random

import pytest

from ville.configuration import Configuration
from ville.donnees.journal import Journal
from ville.moteur.agent import Activite, Perception
from ville.moteur.alea import SourceAlea
from ville.moteur.carte import Carte
from ville.moteur.horloge import SECONDES_PAR_JOUR
from ville.moteur.population import creer_population
from ville.moteur.simulation import Simulation


class JournalMemoire:
    def __init__(self):
        self.evenements = []

    def ecrire(self, evenement):
        self.evenements.append(evenement)


def simuler(carte, heures=24.0, journal=None, decideur=None, **parametres):
    configuration = Configuration(**{"nb_agents": 20, **parametres})
    simulation = Simulation(configuration, carte, journal or JournalMemoire(), decideur)
    for _ in range(int(heures * 3600 / configuration.duree_tick_s)):
        simulation.avancer()
    return simulation


def test_population_de_la_taille_demandee(carte_grille):
    agents = creer_population(Configuration(nb_agents=30), carte_grille, SourceAlea(1))
    assert [agent.identifiant for agent in agents] == list(range(30))


def test_population_respecte_la_configuration(carte_grille):
    configuration = Configuration(nb_agents=200)
    for agent in creer_population(configuration, carte_grille, SourceAlea(1)):
        assert agent.domicile != agent.travail
        assert agent.noeud == agent.domicile
        assert configuration.vitesse_min_m_s <= agent.vitesse_m_s <= configuration.vitesse_max_m_s
        assert 7 * 3600 <= agent.heure_travail_s < 9 * 3600
        assert agent.budget_centimes == configuration.budget_initial_centimes


def test_carte_trop_petite_refusee():
    carte = Carte({"noeuds": [{"id": 1, "lat": 45.0, "lon": 4.0}], "aretes": []})
    with pytest.raises(ValueError, match="deux nœuds"):
        creer_population(Configuration(), carte, SourceAlea(1))


def test_invariants_sur_24_heures(carte_grille):
    configuration = Configuration(nb_agents=20)
    simulation = Simulation(configuration, carte_grille, JournalMemoire())
    for _ in range(24 * 360):
        simulation.avancer()
        for agent in simulation.agents:
            assert agent.noeud in carte_grille.noeuds
            assert agent.budget_centimes >= 0
            if agent.chemin:
                assert carte_grille.contient_arete(agent.noeud, agent.chemin[0])
    assert simulation.horloge.secondes == configuration.heure_depart_s + 24 * 3600


def test_chaque_agent_suit_sa_routine(carte_grille):
    journal = JournalMemoire()
    simuler(carte_grille, heures=24, journal=journal)
    for identifiant in range(20):
        etapes = [
            evenement["etape"]
            for evenement in journal.evenements
            if evenement["type"] == "arrivee" and evenement["agent"] == identifiant
        ]
        assert etapes[0] == "arrivee_travail"
        assert "arrivee_domicile" in etapes


def test_depart_a_l_heure_prevue(carte_grille):
    journal = JournalMemoire()
    simulation = simuler(carte_grille, heures=5, journal=journal)
    departs = [
        evenement
        for evenement in journal.evenements
        if evenement["type"] == "decision" and evenement["intention"].get("motif") == "travail"
    ]
    assert len(departs) == 20
    for depart in departs:
        heure_prevue = simulation.agents[depart["agent"]].heure_travail_s
        assert 0 <= depart["contexte"]["seconde_du_jour"] - heure_prevue < 10


def test_salaire_verse_a_la_fin_du_travail(carte_grille):
    configuration = Configuration(probabilite_loisir=0.0)
    salaire_journee = configuration.salaire_horaire_centimes * 8
    simulation = simuler(carte_grille, heures=20, probabilite_loisir=0.0)
    for agent in simulation.agents:
        assert agent.budget_centimes == configuration.budget_initial_centimes + salaire_journee


def test_loisir_paye(carte_grille):
    configuration = Configuration(probabilite_loisir=1.0)
    salaire_journee = configuration.salaire_horaire_centimes * 8
    simulation = simuler(carte_grille, heures=22, probabilite_loisir=1.0)
    for agent in simulation.agents:
        assert agent.budget_centimes == (
            configuration.budget_initial_centimes
            + salaire_journee
            - configuration.prix_loisir_centimes
        )


class DecideurEspion:
    def __init__(self):
        self.ticks_par_agent = {}

    def decider(self, perception: Perception, flux: Random):
        self.ticks_par_agent.setdefault(perception.agent, []).append(perception.tick)
        return Activite("attente", 100)


def test_decideur_appele_uniquement_pour_les_agents_libres(carte_grille):
    espion = DecideurEspion()
    simuler(carte_grille, heures=1, decideur=espion, nb_agents=3)
    for ticks in espion.ticks_par_agent.values():
        assert ticks == list(range(0, 360, 10))


def test_les_decisions_voient_l_etat_gele_du_debut_de_tick(carte_grille):
    class DecideurLecteur:
        def __init__(self):
            self.simulation = None
            self.libres_vus = []

        def decider(self, perception, flux):
            self.libres_vus.append(
                sum(agent.est_libre for agent in self.simulation.agents)
            )
            return Activite("attente", 3600)

    configuration = Configuration(nb_agents=5)
    decideur = DecideurLecteur()
    simulation = Simulation(configuration, carte_grille, JournalMemoire(), decideur)
    decideur.simulation = simulation
    simulation.avancer()
    assert decideur.libres_vus == [5] * 5


def test_intention_inconnue_refusee(carte_grille):
    class DecideurFautif:
        def decider(self, perception, flux):
            return "partir"

    with pytest.raises(ValueError, match="intention inconnue"):
        simuler(carte_grille, heures=1, decideur=DecideurFautif())


def test_le_journal_reel_accepte_toute_la_simulation(carte_grille):
    sortie = io.StringIO()
    simuler(carte_grille, heures=SECONDES_PAR_JOUR / 3600, journal=Journal(sortie))
    assert sortie.getvalue().endswith("\n")
