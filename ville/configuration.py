from dataclasses import dataclass


@dataclass(frozen=True)
class Configuration:
    graine: int = 42
    nb_agents: int = 100
    duree_tick_s: int = 10
    heure_depart_s: int = 6 * 3600
    vitesse_min_m_s: float = 1.2
    vitesse_max_m_s: float = 1.6
    budget_initial_centimes: int = 10000
    salaire_horaire_centimes: int = 1500
    prix_loisir_centimes: int = 1000
    heure_travail_s: int = 8 * 3600
    dispersion_horaire_s: int = 3600
    duree_travail_s: int = 8 * 3600
    duree_loisir_s: int = 3600
    probabilite_loisir: float = 0.3
