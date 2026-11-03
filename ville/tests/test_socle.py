import importlib


def test_le_paquet_s_importe():
    assert importlib.import_module("ville.moteur") is not None
