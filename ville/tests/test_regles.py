from dataclasses import replace

import pytest

from ville.configuration import Configuration
from ville.moteur.agent import Activite, Aller, Perception
from ville.moteur.alea import SourceAlea
from ville.moteur.regles import DecideurRegles

NOEUDS = [1, 2, 3, 4, 5, 6]


def perception(**champs) -> Perception:
    base = Perception(
        tick=0,
        seconde_du_jour=6 * 3600,
        agent=0,
        noeud=1,
        etape="initial",
        budget_centimes=10000,
        domicile=1,
        travail=3,
        heure_travail_s=8 * 3600,
    )
    return replace(base, **champs)


def decider(configuration=None, **champs):
    decideur = DecideurRegles(configuration or Configuration(), NOEUDS)
    return decideur.decider(perception(**champs), SourceAlea(1).flux("essai"))


def test_au_depart_attend_l_heure_du_travail():
    assert decider() == Activite("attente", 2 * 3600)


def test_rentre_le_soir_attend_le_lendemain():
    assert decider(etape="arrivee_domicile", seconde_du_jour=20 * 3600) == Activite(
        "attente", 12 * 3600
    )


def test_apres_l_attente_part_travailler():
    assert decider(etape="attente") == Aller(3, "travail")


def test_arrive_au_travail_se_met_au_travail():
    assert decider(etape="arrivee_travail") == Activite("travail", 8 * 3600)


@pytest.mark.parametrize("etape", ["inconnue", "arrivee_ailleurs"])
def test_etape_inconnue_refusee(etape):
    with pytest.raises(ValueError, match="étape inconnue"):
        decider(etape=etape)


def test_apres_le_travail_toujours_loisir_si_probabilite_un():
    intention = decider(Configuration(probabilite_loisir=1.0), etape="travail")
    assert isinstance(intention, Aller)
    assert intention.motif == "loisir"
    assert intention.destination in NOEUDS


def test_apres_le_travail_rentre_si_probabilite_zero():
    assert decider(Configuration(probabilite_loisir=0.0), etape="travail") == Aller(1, "domicile")


def test_sans_argent_pas_de_loisir():
    configuration = Configuration(probabilite_loisir=1.0, prix_loisir_centimes=500)
    assert decider(configuration, etape="travail", budget_centimes=499) == Aller(1, "domicile")
    assert decider(configuration, etape="travail", budget_centimes=500).motif == "loisir"


def test_arrive_au_loisir_en_profite_puis_rentre():
    assert decider(etape="arrivee_loisir") == Activite("loisir", 3600)
    assert decider(etape="loisir") == Aller(1, "domicile")


def test_meme_flux_meme_decision():
    decideur = DecideurRegles(Configuration(probabilite_loisir=0.5), NOEUDS)
    suites = [
        [decideur.decider(perception(etape="travail"), source.flux("essai")) for _ in range(50)]
        for source in (SourceAlea(7), SourceAlea(7))
    ]
    assert suites[0] == suites[1]
    assert {intention.motif for intention in suites[0]} == {"loisir", "domicile"}
