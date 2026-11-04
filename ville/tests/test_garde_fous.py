import ast
from pathlib import Path

import pytest

import ville

RACINE = Path(ville.__file__).parent
MODULES_INTERDITS = {"time", "datetime", "uuid", "secrets"}
EXEMPTES_D_HORLOGE = {"__main__.py", "banc.py", "client.py", "mesures.py"}


def fichiers_source():
    return sorted(
        chemin for chemin in RACINE.rglob("*.py") if "tests" not in chemin.relative_to(RACINE).parts
    )


def modules_importes(arbre: ast.AST) -> set[str]:
    modules = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            modules.add(noeud.module.split(".")[0])
    return modules


def lire(chemin: Path) -> ast.AST:
    return ast.parse(chemin.read_text(encoding="utf-8"))


def annotations_seulement(chemin: Path) -> bool:
    arbre = lire(chemin)
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import) and any(a.name == "random" for a in noeud.names):
            return False
        if isinstance(noeud, ast.ImportFrom) and noeud.module == "random":
            if any(alias.name != "Random" for alias in noeud.names):
                return False
    return not any(
        isinstance(noeud, ast.Call)
        and isinstance(noeud.func, ast.Name)
        and noeud.func.id == "Random"
        for noeud in ast.walk(arbre)
    )


def test_il_y_a_des_fichiers_a_verifier():
    noms = {chemin.name for chemin in fichiers_source()}
    assert {"alea.py", "simulation.py", "agent.py"} <= noms


@pytest.mark.parametrize("chemin", fichiers_source(), ids=lambda chemin: chemin.name)
def test_random_reste_confine_a_alea(chemin):
    if chemin.name != "alea.py":
        assert annotations_seulement(chemin)


@pytest.mark.parametrize("chemin", fichiers_source(), ids=lambda chemin: chemin.name)
def test_pas_d_horloge_murale_ni_d_identifiant_aleatoire(chemin):
    if chemin.name not in EXEMPTES_D_HORLOGE:
        assert not modules_importes(lire(chemin)) & MODULES_INTERDITS


@pytest.mark.parametrize("chemin", fichiers_source(), ids=lambda chemin: chemin.name)
def test_pas_de_hash_integre(chemin):
    for noeud in ast.walk(lire(chemin)):
        if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name):
            assert noeud.func.id != "hash"


@pytest.mark.parametrize("chemin", fichiers_source(), ids=lambda chemin: chemin.name)
def test_osmnx_confine_a_preparer_carte(chemin):
    if chemin.name != "preparer_carte.py":
        assert "osmnx" not in modules_importes(lire(chemin))


def test_le_garde_fou_detecte_bien_une_infraction(tmp_path):
    fautif = tmp_path / "fautif.py"
    fautif.write_text("import random\nrandom.random()\n", encoding="utf-8")
    assert not annotations_seulement(fautif)
    annotation = tmp_path / "annotation.py"
    annotation.write_text("from random import Random\nx: Random\n", encoding="utf-8")
    assert annotations_seulement(annotation)
    instanciation = tmp_path / "instanciation.py"
    instanciation.write_text("from random import Random\nRandom(1)\n", encoding="utf-8")
    assert not annotations_seulement(instanciation)
