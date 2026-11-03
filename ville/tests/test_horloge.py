import pytest

from ville.moteur.horloge import SECONDES_PAR_JOUR, Horloge


def test_conversion_du_tick_en_secondes():
    horloge = Horloge(duree_tick_s=10, heure_depart_s=3600)
    horloge.avancer()
    horloge.avancer()
    assert horloge.tick == 2
    assert horloge.secondes == 3620


def test_passage_de_minuit():
    horloge = Horloge(duree_tick_s=10, heure_depart_s=SECONDES_PAR_JOUR - 10)
    assert (horloge.jour, horloge.seconde_du_jour) == (0, SECONDES_PAR_JOUR - 10)
    horloge.avancer()
    assert (horloge.jour, horloge.seconde_du_jour) == (1, 0)


def test_aucune_derive_apres_un_million_de_ticks():
    horloge = Horloge(duree_tick_s=7)
    for _ in range(1_000_000):
        horloge.avancer()
    assert horloge.secondes == 7_000_000


@pytest.mark.parametrize("duree", [0, -1, 1.5])
def test_duree_invalide_refusee(duree):
    with pytest.raises(ValueError):
        Horloge(duree_tick_s=duree)


@pytest.mark.parametrize("secondes,attendu", [(0, 0), (1, 1), (10, 1), (11, 2), (100, 10)])
def test_une_duree_est_arrondie_au_tick_superieur(secondes, attendu):
    assert Horloge(duree_tick_s=10).ticks_pour(secondes) == attendu
