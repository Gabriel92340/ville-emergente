import platform
from dataclasses import asdict

from ville.configuration import Configuration
from ville.moteur.agent import (
    LOISIR,
    TRAVAIL,
    Agent,
    Aller,
    Decideur,
    Intention,
    Perception,
    intention_en_dict,
)
from ville.moteur.alea import SourceAlea
from ville.moteur.carte import Carte
from ville.moteur.horloge import Horloge
from ville.moteur.population import creer_population
from ville.moteur.regles import DecideurRegles


class Simulation:
    def __init__(
        self,
        configuration: Configuration,
        carte: Carte,
        journal,
        decideur: Decideur | None = None,
    ):
        self.configuration = configuration
        self.carte = carte
        self.journal = journal
        self.alea = SourceAlea(configuration.graine)
        self.horloge = Horloge(configuration.duree_tick_s, configuration.heure_depart_s)
        self.agents = creer_population(configuration, carte, self.alea)
        self.decideur = decideur or DecideurRegles(configuration, carte.noeuds)
        self.nb_decisions = 0
        self.journal.ecrire(
            {
                "type": "entete",
                "graine": configuration.graine,
                "configuration": asdict(configuration),
                "empreinte_carte": carte.empreinte,
                "python": platform.python_version(),
            }
        )

    def avancer(self) -> None:
        intentions = self._decider()
        for agent, intention in intentions:
            self._appliquer(agent, intention)
        for agent in self.agents:
            self._progresser(agent)
        self.horloge.avancer()

    def _decider(self) -> list[tuple[Agent, Intention]]:
        intentions = []
        for agent in self.agents:
            if agent.est_libre:
                intentions.append((agent, self._faire_decider(agent)))
        return intentions

    def _faire_decider(self, agent: Agent) -> Intention:
        nom_flux = f"agents/{agent.identifiant}/decision"
        perception = self._percevoir(agent)
        intention = self.decideur.decider(perception, self.alea.flux(nom_flux))
        self.nb_decisions += 1
        self.journal.ecrire(
            {
                "type": "decision",
                "tick": self.horloge.tick,
                "agent": agent.identifiant,
                "graine": self.configuration.graine,
                "flux": nom_flux,
                "contexte": asdict(perception),
                "intention": intention_en_dict(intention),
                "reponse_brute": None,
            }
        )
        return intention

    def _percevoir(self, agent: Agent) -> Perception:
        return Perception(
            tick=self.horloge.tick,
            seconde_du_jour=self.horloge.seconde_du_jour,
            agent=agent.identifiant,
            noeud=agent.noeud,
            etape=agent.etape,
            budget_centimes=agent.budget_centimes,
            domicile=agent.domicile,
            travail=agent.travail,
            heure_travail_s=agent.heure_travail_s,
        )

    def _appliquer(self, agent: Agent, intention: Intention) -> None:
        if isinstance(intention, Aller):
            chemin = self.carte.plus_court_chemin(agent.noeud, intention.destination)
            agent.commencer_trajet(chemin, intention.motif)
        else:
            ticks = max(1, self.horloge.ticks_pour(intention.duree_s))
            agent.commencer_activite(intention.nature, intention.duree_s, self.horloge.tick + ticks)

    def _progresser(self, agent: Agent) -> None:
        if agent.est_en_trajet:
            distance = agent.vitesse_m_s * self.configuration.duree_tick_s
            if agent.avancer(distance, self.carte):
                self.journal.ecrire(
                    {
                        "type": "arrivee",
                        "tick": self.horloge.tick,
                        "agent": agent.identifiant,
                        "noeud": agent.noeud,
                        "etape": agent.etape,
                    }
                )
        elif agent.activite is not None and self.horloge.tick + 1 >= agent.fin_activite_tick:
            self._regler_activite(agent)
            agent.terminer_activite()

    def _regler_activite(self, agent: Agent) -> None:
        if agent.activite == TRAVAIL:
            salaire = self.configuration.salaire_horaire_centimes * agent.duree_activite_s
            agent.budget_centimes += salaire // 3600
        elif agent.activite == LOISIR:
            agent.budget_centimes -= self.configuration.prix_loisir_centimes
