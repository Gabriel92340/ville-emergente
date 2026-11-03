import json

import pytest

from ville.moteur.carte import Carte, CheminIntrouvable
from ville.tests.conftest import donnees_grille


def test_noeuds_tries(carte_grille):
    assert carte_grille.noeuds == [1, 2, 3, 4, 5, 6]


def test_plus_court_chemin_calcule_a_la_main():
    donnees = {
        "noeuds": [{"id": i, "lat": 45.0, "lon": 4.0} for i in (1, 2, 3)],
        "aretes": [
            {"origine": 1, "destination": 3, "longueur": 500.0},
            {"origine": 1, "destination": 2, "longueur": 100.0},
            {"origine": 2, "destination": 3, "longueur": 100.0},
        ],
    }
    assert Carte(donnees).plus_court_chemin(1, 3) == [1, 2, 3]


def test_chemin_vers_soi_meme(carte_grille):
    assert carte_grille.plus_court_chemin(3, 3) == [3]


def test_destination_inaccessible_donne_une_erreur_claire():
    donnees = {
        "noeuds": [{"id": i, "lat": 45.0, "lon": 4.0} for i in (1, 2)],
        "aretes": [{"origine": 1, "destination": 2, "longueur": 10.0}],
    }
    carte = Carte(donnees)
    with pytest.raises(CheminIntrouvable, match="aucun chemin de 2 vers 1"):
        carte.plus_court_chemin(2, 1)


def test_noeud_inconnu_donne_une_erreur_claire(carte_grille):
    with pytest.raises(CheminIntrouvable):
        carte_grille.plus_court_chemin(1, 999)


def test_modifier_le_chemin_rendu_ne_corrompt_pas_le_cache(carte_grille):
    chemin = carte_grille.plus_court_chemin(1, 3)
    chemin.append(999)
    assert carte_grille.plus_court_chemin(1, 3) == [1, 2, 3]


def test_interpolation_au_milieu_d_une_arete(carte_grille):
    lat, lon = carte_grille.interpoler(1, 2, 50.0)
    assert lat == pytest.approx(45.001)
    assert lon == pytest.approx(4.0005)


def test_interpolation_aux_extremites(carte_grille):
    assert carte_grille.interpoler(1, 2, 0.0) == pytest.approx(carte_grille.coordonnees(1))
    assert carte_grille.interpoler(1, 2, 100.0) == pytest.approx(carte_grille.coordonnees(2))


def test_empreinte_independante_de_l_ordre_d_insertion():
    normal = donnees_grille()
    inverse = {
        "noeuds": list(reversed(normal["noeuds"])),
        "aretes": list(reversed(normal["aretes"])),
    }
    assert Carte(normal).empreinte == Carte(inverse).empreinte


def test_egalites_de_chemin_independantes_de_l_ordre_d_insertion():
    normal = donnees_grille()
    inverse = {
        "noeuds": list(reversed(normal["noeuds"])),
        "aretes": list(reversed(normal["aretes"])),
    }
    assert Carte(normal).plus_court_chemin(1, 6) == Carte(inverse).plus_court_chemin(1, 6)


def test_empreinte_change_si_la_carte_change():
    modifiee = donnees_grille()
    modifiee["aretes"][0]["longueur"] = 101.0
    assert Carte(donnees_grille()).empreinte != Carte(modifiee).empreinte


def test_aretes_paralleles_reduites_a_la_plus_courte():
    donnees = {
        "noeuds": [{"id": i, "lat": 45.0, "lon": 4.0} for i in (1, 2)],
        "aretes": [
            {"origine": 1, "destination": 2, "longueur": 30.0},
            {"origine": 1, "destination": 2, "longueur": 10.0},
            {"origine": 1, "destination": 2, "longueur": 20.0},
        ],
    }
    assert Carte(donnees).longueur(1, 2) == 10.0


def test_boucle_sur_soi_ignoree():
    donnees = {
        "noeuds": [{"id": 1, "lat": 45.0, "lon": 4.0}],
        "aretes": [{"origine": 1, "destination": 1, "longueur": 5.0}],
    }
    assert not Carte(donnees).contient_arete(1, 1)


@pytest.mark.parametrize(
    "aretes",
    [
        [{"origine": 1, "destination": 99, "longueur": 1.0}],
        [{"origine": 1, "destination": 2, "longueur": 0.0}],
        [{"origine": 1, "destination": 2, "longueur": -1.0}],
    ],
)
def test_donnees_invalides_refusees(aretes):
    donnees = {"noeuds": [{"id": i, "lat": 45.0, "lon": 4.0} for i in (1, 2)], "aretes": aretes}
    with pytest.raises(ValueError):
        Carte(donnees)


def test_noeud_en_double_refuse():
    donnees = {"noeuds": [{"id": 1, "lat": 45.0, "lon": 4.0}] * 2, "aretes": []}
    with pytest.raises(ValueError):
        Carte(donnees)


def test_connexite(carte_grille):
    assert carte_grille.est_fortement_connexe()
    sens_unique = {
        "noeuds": [{"id": i, "lat": 45.0, "lon": 4.0} for i in (1, 2)],
        "aretes": [{"origine": 1, "destination": 2, "longueur": 10.0}],
    }
    assert not Carte(sens_unique).est_fortement_connexe()


def test_chargement_depuis_un_fichier(tmp_path, carte_grille):
    chemin = tmp_path / "carte.json"
    chemin.write_text(json.dumps(donnees_grille()), encoding="utf-8")
    assert Carte.charger(chemin).empreinte == carte_grille.empreinte
