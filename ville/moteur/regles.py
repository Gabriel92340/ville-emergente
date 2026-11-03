from random import Random

from ville.configuration import Configuration
from ville.moteur.agent import (
    ATTENTE,
    DOMICILE,
    ETAPE_INITIALE,
    LOISIR,
    PREFIXE_ARRIVEE,
    TRAVAIL,
    Activite,
    Aller,
    Intention,
    Perception,
)
from ville.moteur.horloge import SECONDES_PAR_JOUR


class DecideurRegles:
    def __init__(self, configuration: Configuration, noeuds: list[int]):
        self._configuration = configuration
        self._noeuds = noeuds

    def decider(self, perception: Perception, flux: Random) -> Intention:
        etape = perception.etape
        if etape in (ETAPE_INITIALE, PREFIXE_ARRIVEE + DOMICILE):
            attente = (perception.heure_travail_s - perception.seconde_du_jour) % SECONDES_PAR_JOUR
            return Activite(ATTENTE, attente)
        if etape == ATTENTE:
            return Aller(perception.travail, TRAVAIL)
        if etape == PREFIXE_ARRIVEE + TRAVAIL:
            return Activite(TRAVAIL, self._configuration.duree_travail_s)
        if etape == TRAVAIL:
            return self._apres_le_travail(perception, flux)
        if etape == PREFIXE_ARRIVEE + LOISIR:
            return Activite(LOISIR, self._configuration.duree_loisir_s)
        if etape == LOISIR:
            return Aller(perception.domicile, DOMICILE)
        raise ValueError(f"étape inconnue : {etape}")

    def _apres_le_travail(self, perception: Perception, flux: Random) -> Intention:
        tirage = flux.random()
        peut_payer = perception.budget_centimes >= self._configuration.prix_loisir_centimes
        if tirage < self._configuration.probabilite_loisir and peut_payer:
            indice = int(flux.random() * len(self._noeuds))
            return Aller(self._noeuds[indice], LOISIR)
        return Aller(perception.domicile, DOMICILE)
