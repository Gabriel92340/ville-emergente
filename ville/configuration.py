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


@dataclass(frozen=True)
class ConfigurationCerveau:
    modele: str = "qwen2.5:3b"
    quota_agents: int = 5
    periode_ticks: int = 6
    delai_ticks: int = 6
    taille_memoire: int = 12
    lieux_connus: int = 3
    etapes_max: int = 3
    duree_max_minutes: int = 720
    temperature: float = 0.7
    nb_jetons_max: int = 300

    def __post_init__(self):
        if self.delai_ticks < 1:
            raise ValueError("le délai de réflexion doit être d'au moins un tick")
