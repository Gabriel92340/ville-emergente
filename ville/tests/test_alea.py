import os
import subprocess
import sys

from ville.moteur.alea import SourceAlea


def tirer(source, nom, nombre=5):
    return [source.flux(nom).random() for _ in range(nombre)]


def test_meme_graine_donne_meme_suite():
    assert tirer(SourceAlea(42), "a") == tirer(SourceAlea(42), "a")


def test_graines_differentes_donnent_suites_differentes():
    assert tirer(SourceAlea(42), "a") != tirer(SourceAlea(43), "a")


def test_noms_differents_donnent_suites_differentes():
    source = SourceAlea(42)
    assert tirer(source, "a") != tirer(source, "b")


def test_le_meme_nom_rend_le_meme_flux():
    source = SourceAlea(42)
    assert source.flux("a") is source.flux("a")


def test_consommer_un_flux_ne_decale_pas_un_autre():
    temoin = tirer(SourceAlea(42), "b")
    source = SourceAlea(42)
    tirer(source, "a", nombre=1000)
    assert tirer(source, "b") == temoin


def test_ordre_de_creation_des_flux_sans_effet():
    premiere = SourceAlea(42)
    premiere.flux("a")
    seconde = SourceAlea(42)
    seconde.flux("b")
    seconde.flux("a")
    assert tirer(premiere, "a") == tirer(seconde, "a")


def test_valeurs_identiques_entre_processus():
    programme = (
        "from ville.moteur.alea import SourceAlea;"
        "print(SourceAlea(42).flux('agents/17/decision').random())"
    )
    sorties = set()
    for valeur in ("0", "1", "12345"):
        environnement = {**os.environ, "PYTHONHASHSEED": valeur}
        resultat = subprocess.run(
            [sys.executable, "-c", programme],
            env=environnement,
            capture_output=True,
            text=True,
            check=True,
        )
        sorties.add(resultat.stdout)
    assert len(sorties) == 1
