from random import Random

from ville.configuration import Configuration
from ville.moteur.agent import Agent
from ville.moteur.alea import SourceAlea
from ville.moteur.carte import Carte


def _tirer_noeud(noeuds: list[int], flux: Random) -> int:
    return noeuds[int(flux.random() * len(noeuds))]


def creer_agent(identifiant: int, configuration: Configuration, carte: Carte, alea: SourceAlea) -> Agent:
    flux = alea.flux(f"agents/{identifiant}/creation")
    domicile = _tirer_noeud(carte.noeuds, flux)
    travail = _tirer_noeud(carte.noeuds, flux)
    while travail == domicile:
        travail = _tirer_noeud(carte.noeuds, flux)
    ecart_vitesse = configuration.vitesse_max_m_s - configuration.vitesse_min_m_s
    dispersion = configuration.dispersion_horaire_s
    return Agent(
        identifiant=identifiant,
        domicile=domicile,
        travail=travail,
        vitesse_m_s=configuration.vitesse_min_m_s + flux.random() * ecart_vitesse,
        heure_travail_s=configuration.heure_travail_s - dispersion + int(flux.random() * 2 * dispersion),
        budget_centimes=configuration.budget_initial_centimes,
        noeud=domicile,
    )


def creer_population(configuration: Configuration, carte: Carte, alea: SourceAlea) -> list[Agent]:
    if len(carte.noeuds) < 2:
        raise ValueError("la carte doit contenir au moins deux nœuds")
    return [
        creer_agent(identifiant, configuration, carte, alea)
        for identifiant in range(configuration.nb_agents)
    ]
