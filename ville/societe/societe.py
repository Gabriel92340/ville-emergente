from dataclasses import asdict

from ville.configuration import ConfigurationSociete
from ville.moteur.agent import LOISIR, TRAVAIL, Agent
from ville.societe.economie import Economie
from ville.societe.election import Candidat, Election
from ville.societe.relations import Relations
from ville.societe.rencontres import DetecteurRencontres, en_metres
from ville.societe.rumeurs import Rumeurs
from ville.societe.scenarios import ELECTION, PLUIE_ARGENT, RUMEUR, valider_scenario

VERSION_CONTEXTE = "1"
CHOIX_RUMEURS = "repeter_rumeurs"
CHOIX_VOTE = "vote"
RELATIONS_DANS_LE_PROMPT = 3


class Societe:
    def __init__(self, configuration: ConfigurationSociete, scenario: list[dict] | None = None):
        self.configuration = configuration
        self.scenario = list(scenario or [])
        self.relations = Relations()
        self.rumeurs = Rumeurs(configuration.probabilite_transmission)
        self.election: Election | None = None
        self.nb_rencontres = 0
        self._detecteur = DetecteurRencontres(configuration.rayon_rencontre_m)
        self._volontes: dict[int, bool] = {}

    def description(self) -> dict:
        return {
            "configuration": asdict(self.configuration),
            "scenario": self.scenario,
            "version_contexte": VERSION_CONTEXTE,
        }

    def demarrer(self, simulation) -> None:
        self._simulation = simulation
        self._evenements = valider_scenario(self.scenario, len(simulation.agents))
        noeuds = simulation.carte.noeuds
        if len(noeuds) < self.configuration.nb_commerces:
            raise ValueError("la carte a moins de nœuds que de commerces")
        restants = list(noeuds)
        flux = simulation.alea.flux("societe/commerces")
        for position in range(self.configuration.nb_commerces):
            autre = position + int(flux.random() * (len(restants) - position))
            restants[position], restants[autre] = restants[autre], restants[position]
        self.noeuds_commerces = sorted(restants[: self.configuration.nb_commerces])
        self.economie = Economie(self.configuration, self.noeuds_commerces)
        self.monnaie_initiale = self.economie.monnaie_totale(simulation.agents)
        latitudes = [simulation.carte.coordonnees(noeud)[0] for noeud in noeuds]
        self._latitude_reference = sum(latitudes) / len(latitudes)

    def _ecrire(self, tick: int, evenement: dict) -> None:
        self._simulation.journal.ecrire({"tick": tick, **evenement})

    def tour(self, tick: int) -> None:
        while self._evenements and self._evenements[0]["tick"] == tick:
            self._declencher(self._evenements.pop(0), tick)
        if self.election is not None and self.election.tick_vote == tick:
            self._depouiller(tick)
        if tick > 0 and tick % self.configuration.periode_prix_ticks == 0:
            for evenement in self.economie.ajuster_prix():
                self._ecrire(tick, evenement)
        if tick > 0 and tick % self.configuration.periode_redistribution_ticks == 0:
            evenement = self.economie.redistribuer(self._simulation.agents)
            if evenement is not None:
                self._ecrire(tick, evenement)

    def _declencher(self, evenement: dict, tick: int) -> None:
        nature = evenement["type"]
        if nature == PLUIE_ARGENT:
            montant = evenement["montant_centimes"]
            self._ecrire(tick, self.economie.injecter(self._simulation.agents, montant))
        elif nature == RUMEUR:
            self._ecrire(tick, self.rumeurs.injecter(evenement["contenu"], evenement["source"], tick))
        elif nature == ELECTION:
            candidats = [
                Candidat(candidat["agent"], candidat["taux_impot_pourcent"])
                for candidat in evenement["candidats"]
            ]
            self.election = Election(candidats, evenement["tick_vote"])
            self._ecrire(
                tick,
                {
                    "type": "election_ouverte",
                    "candidats": evenement["candidats"],
                    "tick_vote": evenement["tick_vote"],
                },
            )

    def _depouiller(self, tick: int) -> None:
        alea = self._simulation.alea
        elu, resultat = self.election.depouiller(
            [agent.identifiant for agent in self._simulation.agents],
            self.relations,
            lambda votant: alea.flux(f"agents/{votant}/vote"),
            alea.flux("societe/election"),
        )
        self.economie.taux_impot_pourcent = elu.taux_impot_pourcent
        self.election = None
        self._ecrire(tick, resultat)

    def regler_activite(self, agent: Agent, salaire_du: int) -> None:
        tick = self._simulation.horloge.tick
        if agent.activite == TRAVAIL:
            evenement = self.economie.payer_salaire(agent, salaire_du, agent.duree_activite_s)
            self._ecrire(tick, evenement)
        elif agent.activite == LOISIR:
            commerce = self.economie.commerce_au_noeud(agent.noeud)
            if commerce is not None:
                self._ecrire(tick, self.economie.acheter(agent, commerce))

    def apres_progression(self, tick: int) -> None:
        simulation = self._simulation
        positions = {
            agent.identifiant: en_metres(*agent.position(simulation.carte), self._latitude_reference)
            for agent in simulation.agents
        }
        for a, b in self._detecteur.actualiser(positions):
            self.nb_rencontres += 1
            score = self.relations.modifier(a, b, self.configuration.gain_relation_rencontre)
            self._ecrire(tick, {"type": "rencontre", "a": a, "b": b, "score": score})
            for evenement in self.rumeurs.transmettre(
                a,
                b,
                tick,
                self._volontes.get,
                lambda rumeur: simulation.alea.flux(f"rumeurs/{rumeur}"),
            ):
                self._ecrire(tick, evenement)

    def contexte_agent(self, agent: int) -> str | None:
        lignes = [f"Impôt actuel sur les salaires : {self.economie.taux_impot_pourcent} %."]
        connues = self.rumeurs.connues_par(agent)
        if connues:
            lignes.append("Rumeurs entendues : " + " ; ".join(r.contenu for r in connues) + ".")
            lignes.append(
                f"Indique dans « {CHOIX_RUMEURS} » si tu répètes ces rumeurs à qui tu croises."
            )
        meilleures = self.relations.meilleures(agent, RELATIONS_DANS_LE_PROMPT)
        if meilleures:
            texte = ", ".join(f"habitant n°{autre} ({score})" for autre, score in meilleures)
            lignes.append(f"Personnes que tu connais (score) : {texte}.")
        if self.election is not None:
            offres = ", ".join(
                f"{candidat.nom} (impôt {candidat.taux_impot_pourcent} %)"
                for candidat in self.election.candidats
            )
            lignes.append(f"Élection en cours. Candidats : {offres}.")
            lignes.append(f"Indique ton choix dans « {CHOIX_VOTE} ».")
        return "\n".join(lignes)

    def choix_attendus(self, agent: int) -> dict[str, list[str] | None]:
        attendus: dict[str, list[str] | None] = {}
        if self.rumeurs.connues_par(agent):
            attendus[CHOIX_RUMEURS] = None
        if self.election is not None:
            attendus[CHOIX_VOTE] = self.election.noms()
        return attendus

    def enregistrer_choix(self, agent: int, choix: dict) -> None:
        if CHOIX_RUMEURS in choix:
            self._volontes[agent] = choix[CHOIX_RUMEURS]
        if CHOIX_VOTE in choix and self.election is not None:
            if choix[CHOIX_VOTE] in self.election.noms():
                self.election.enregistrer_vote(agent, choix[CHOIX_VOTE])
