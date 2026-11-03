import json
import os
import subprocess
import sys

import pytest

from ville.tests.conftest import donnees_grille

HEURES = "24"


@pytest.fixture
def fichier_carte(tmp_path):
    chemin = tmp_path / "carte.json"
    chemin.write_text(json.dumps(donnees_grille()), encoding="utf-8")
    return chemin


def executer(fichier_carte, journal, graine=42, agents=30, hash_seed="0"):
    resultat = subprocess.run(
        [
            sys.executable,
            "-m",
            "ville.moteur",
            "--graine",
            str(graine),
            "--heures",
            HEURES,
            "--agents",
            str(agents),
            "--carte",
            str(fichier_carte),
            "--journal",
            str(journal),
        ],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        capture_output=True,
        text=True,
    )
    assert resultat.returncode == 0, resultat.stderr
    return journal.read_bytes()


def decisions_par_agent(contenu: bytes, limite: int) -> list[bytes]:
    return [
        ligne
        for ligne in contenu.splitlines()
        if json.loads(ligne)["type"] != "entete" and json.loads(ligne)["agent"] < limite
    ]


def test_meme_graine_donne_un_journal_identique_a_l_octet(fichier_carte, tmp_path):
    premier = executer(fichier_carte, tmp_path / "a.jsonl", hash_seed="1")
    second = executer(fichier_carte, tmp_path / "b.jsonl", hash_seed="98765")
    assert len(premier) > 0
    assert premier == second


def test_autre_graine_donne_un_journal_different(fichier_carte, tmp_path):
    premier = executer(fichier_carte, tmp_path / "a.jsonl", graine=42)
    second = executer(fichier_carte, tmp_path / "b.jsonl", graine=43)
    assert premier != second


def test_ajouter_des_agents_ne_change_pas_les_premiers(fichier_carte, tmp_path):
    cent = executer(fichier_carte, tmp_path / "a.jsonl", agents=100)
    cent_vingt = executer(fichier_carte, tmp_path / "b.jsonl", agents=120)
    assert cent != cent_vingt
    assert decisions_par_agent(cent, 100) == decisions_par_agent(cent_vingt, 100)


def test_carte_absente_donne_une_erreur_claire(tmp_path):
    resultat = subprocess.run(
        [sys.executable, "-m", "ville.moteur", "--carte", str(tmp_path / "absente.json")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert resultat.returncode == 2
    assert "carte introuvable" in resultat.stderr
