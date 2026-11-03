import pytest

from ville.moteur.agent import (
    TRAVAIL,
    Activite,
    Agent,
    Aller,
    intention_en_dict,
)


def agent_au_noeud(noeud=1):
    return Agent(
        identifiant=0,
        domicile=noeud,
        travail=3,
        vitesse_m_s=1.0,
        heure_travail_s=0,
        budget_centimes=0,
        noeud=noeud,
    )


def test_avance_a_vitesse_connue_sur_une_arete(carte_grille):
    agent = agent_au_noeud()
    agent.commencer_trajet([1, 2, 3], TRAVAIL)
    assert agent.avancer(40.0, carte_grille) is False
    assert (agent.noeud, agent.chemin, agent.distance_sur_arete) == (1, [2, 3], 40.0)
    assert agent.est_en_trajet


def test_enchaine_plusieurs_aretes_en_un_appel(carte_grille):
    agent = agent_au_noeud()
    agent.commencer_trajet([1, 2, 3, 6], TRAVAIL)
    assert agent.avancer(230.0, carte_grille) is False
    assert (agent.noeud, agent.chemin) == (3, [6])
    assert agent.distance_sur_arete == pytest.approx(30.0)


def test_arrivee_exacte_sans_depassement(carte_grille):
    agent = agent_au_noeud()
    agent.commencer_trajet([1, 2], TRAVAIL)
    assert agent.avancer(100.0, carte_grille) is True
    assert (agent.noeud, agent.chemin, agent.distance_sur_arete) == (2, [], 0.0)
    assert agent.etape == "arrivee_travail"
    assert agent.est_libre


def test_la_distance_en_trop_n_est_pas_comptee(carte_grille):
    agent = agent_au_noeud()
    agent.commencer_trajet([1, 2], TRAVAIL)
    assert agent.avancer(1000.0, carte_grille) is True
    assert agent.noeud == 2
    assert agent.distance_parcourue == 100.0


def test_trajet_vers_sa_propre_position_arrive_aussitot(carte_grille):
    agent = agent_au_noeud()
    agent.commencer_trajet([1], TRAVAIL)
    assert agent.avancer(0.0, carte_grille) is True
    assert agent.noeud == 1


def test_chemin_qui_ne_part_pas_de_la_position_refuse():
    with pytest.raises(ValueError):
        agent_au_noeud().commencer_trajet([2, 3], TRAVAIL)


def test_position_toujours_sur_le_graphe(carte_grille):
    agent = agent_au_noeud()
    agent.commencer_trajet([1, 2, 3, 6], TRAVAIL)
    arrive = False
    while not arrive:
        arrive = agent.avancer(14.0, carte_grille)
        if agent.chemin:
            assert carte_grille.contient_arete(agent.noeud, agent.chemin[0])
            assert 0.0 <= agent.distance_sur_arete < carte_grille.longueur(
                agent.noeud, agent.chemin[0]
            )
    assert agent.distance_parcourue == pytest.approx(300.0)


def test_position_interpolee_en_cours_de_trajet(carte_grille):
    agent = agent_au_noeud()
    agent.commencer_trajet([1, 2], TRAVAIL)
    agent.avancer(50.0, carte_grille)
    assert agent.position(carte_grille) == pytest.approx(carte_grille.interpoler(1, 2, 50.0))


def test_position_a_l_arret_sur_le_noeud(carte_grille):
    assert agent_au_noeud().position(carte_grille) == carte_grille.coordonnees(1)


def test_une_activite_occupe_l_agent_puis_devient_son_etape():
    agent = agent_au_noeud()
    agent.commencer_activite(TRAVAIL, 60, 6)
    assert not agent.est_libre
    agent.terminer_activite()
    assert agent.est_libre
    assert agent.etape == TRAVAIL


def test_intention_serialisable():
    assert intention_en_dict(Aller(3, TRAVAIL)) == {
        "type": "Aller",
        "destination": 3,
        "motif": "travail",
    }
    assert intention_en_dict(Activite(TRAVAIL, 60)) == {
        "type": "Activite",
        "nature": "travail",
        "duree_s": 60,
    }
