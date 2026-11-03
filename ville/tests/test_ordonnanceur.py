from collections import Counter

import pytest

from ville.cerveau.ordonnanceur import Ordonnanceur
from ville.moteur.alea import SourceAlea


def ordonnanceur(quota=5, periode=6, graine=1):
    return Ordonnanceur(quota, periode, SourceAlea(graine).flux("essai"))


def test_tour_de_reflexion_selon_la_periode():
    tours = [t for t in range(20) if ordonnanceur(periode=6).est_tour_de_reflexion(t)]
    assert tours == [0, 6, 12, 18]


def test_quota_respecte_sans_doublon():
    tires = ordonnanceur(quota=5).tirer(list(range(100)))
    assert len(tires) == 5 == len(set(tires))
    assert tires == sorted(tires)


def test_moins_de_candidats_que_de_quota():
    assert ordonnanceur(quota=5).tirer([7, 3]) == [3, 7]
    assert ordonnanceur(quota=5).tirer([]) == []


def test_quota_nul():
    assert ordonnanceur(quota=0).tirer([1, 2, 3]) == []


def test_tirage_reproductible_et_independant_de_l_ordre_des_candidats():
    assert ordonnanceur(graine=4).tirer(list(range(100))) == ordonnanceur(graine=4).tirer(
        list(reversed(range(100)))
    )


def test_graines_differentes_tirages_differents():
    assert ordonnanceur(graine=1).tirer(list(range(100))) != ordonnanceur(graine=2).tirer(
        list(range(100))
    )


def test_tirage_equitable_sur_la_duree():
    instance = ordonnanceur(quota=5)
    compte = Counter()
    for _ in range(2000):
        compte.update(instance.tirer(list(range(100))))
    assert set(compte) == set(range(100))
    assert max(compte.values()) < 2 * min(compte.values())


@pytest.mark.parametrize("quota,periode", [(-1, 6), (5, 0)])
def test_parametres_invalides(quota, periode):
    with pytest.raises(ValueError):
        ordonnanceur(quota=quota, periode=periode)
