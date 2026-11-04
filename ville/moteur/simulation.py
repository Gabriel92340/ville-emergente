import platform
from dataclasses import asdict

from ville.configuration import Configuration
from ville.moteur.agent import (
    LOISIR,
    TRAVAIL,
    Agent,
    Aller,
    Cerveau,
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
        cerveau: Cerveau | None = None,
        societe=None,
    ):
        self.configuration = configuration
        self.carte = carte
        self.journal = journal
        self.alea = SourceAlea(configuration.graine)
        self.horloge = Horloge(configuration.duree_tick_s, configuration.heure_depart_s)
        self.agents = creer_population(configuration, carte, self.alea)
        self.societe = societe
        self.noeuds_loisir = carte.noeuds
        if societe is not None:
            societe.demarrer(self)
            self.noeuds_loisir = societe.noeuds_commerces
        self.decideur = decideur or DecideurRegles(configuration, self.noeuds_loisir)
        self.cerveau = cerveau
        self.nb_decisions = 0
        entete = {
            "type": "entete",
            "graine": configuration.graine,
            "configuration": asdict(configuration),
            "empreinte_carte": carte.empreinte,
            "python": platform.python_version(),
        }
        if societe is not None:
            entete["societe"] = societe.description()
        if cerveau is not None:
            entete["cerveau"] = cerveau.description()
            cerveau.demarrer(self)
        self.journal.ecrire(entete)

    def avancer(self) -> None:
        if self.societe is not None:
            self.societe.tour(self.horloge.tick)
        if self.cerveau is not None:
            self.cerveau.tour(self.horloge.tick)
        intentions = self._decider()
        for agent, intention in intentions:
            self._appliquer(agent, intention)
        for agent in self._ordre_de_progression():
            self._progresser(agent)
        if self.societe is not None:
            self.societe.apres_progression(self.horloge.tick)
        self.horloge.avancer()

    def _ordre_de_progression(self) -> list[Agent]:
        if self.societe is None:
            return self.agents
        ordre = list(self.agents)
        flux = self.alea.flux("societe/ordre")
        for position in range(len(ordre) - 1):
            autre = position + int(flux.random() * (len(ordre) - position))
            ordre[position], ordre[autre] = ordre[autre], ordre[position]
        return ordre

    def prix_loisir(self) -> int:
        if self.societe is None:
            return self.configuration.prix_loisir_centimes
        return self.societe.economie.prix_moyen()

    def _decider(self) -> list[tuple[Agent, Intention]]:
        intentions = []
        for agent in self.agents:
            if agent.est_libre:
                intentions.append((agent, self._faire_decider(agent)))
        return intentions

    def _faire_decider(self, agent: Agent) -> Intention:
        nom_flux = f"agents/{agent.identifiant}/decision"
        perception = self.percevoir(agent)
        flux = self.alea.flux(nom_flux)
        if self.cerveau is None:
            intention, source = self.decideur.decider(perception, flux), None
        else:
            intention, source = self.cerveau.decider(perception, flux)
        self.nb_decisions += 1
        evenement = {
            "type": "decision",
            "tick": self.horloge.tick,
            "agent": agent.identifiant,
            "graine": self.configuration.graine,
            "flux": nom_flux,
            "contexte": asdict(perception),
            "intention": intention_en_dict(intention),
            "reponse_brute": None,
        }
        if source is not None:
            evenement["source"] = source
        self._consigner(evenement)
        return intention

    def _consigner(self, evenement: dict) -> None:
        self.journal.ecrire(evenement)
        if self.cerveau is not None:
            self.cerveau.observer(evenement)

    def percevoir(self, agent: Agent) -> Perception:
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
                self._consigner(
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
        if self.societe is not None:
            salaire = self.configuration.salaire_horaire_centimes * agent.duree_activite_s
            self.societe.regler_activite(agent, salaire // 3600)
        elif agent.activite == TRAVAIL:
            salaire = self.configuration.salaire_horaire_centimes * agent.duree_activite_s
            agent.budget_centimes += salaire // 3600
        elif agent.activite == LOISIR:
            agent.budget_centimes -= self.configuration.prix_loisir_centimes
