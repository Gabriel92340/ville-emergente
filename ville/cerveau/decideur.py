from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from random import Random

from ville.cerveau.client import Client, DemandeModele, ErreurModele
from ville.cerveau.memoire import Memoire
from ville.cerveau.ordonnanceur import Ordonnanceur
from ville.cerveau.plan import LIEU_DOMICILE, LIEU_TRAVAIL, PlanJour
from ville.cerveau.prompts import VERSION_PROMPT, construire_prompt, heure_lisible
from ville.cerveau.reponses import (
    ReponseInvalide,
    ajouter_choix,
    analyser_choix,
    analyser_plan,
    schema_plan,
)
from ville.configuration import ConfigurationCerveau
from ville.donnees.mesures import Mesures
from ville.moteur.agent import DOMICILE, PREFIXE_ARRIVEE, Aller, Intention, Perception
from ville.moteur.horloge import SECONDES_PAR_JOUR

SOURCE_LLM = "llm"
SOURCE_REGLES = "regles"


@dataclass
class _Reflexion:
    demande: DemandeModele
    futur: Future
    echeance: int
    flux: str
    choix_attendus: dict


class CerveauLLM:
    def __init__(
        self,
        configuration: ConfigurationCerveau,
        client: Client,
        ouvriers: int = 1,
        mesures: Mesures | None = None,
    ):
        self.configuration = configuration
        self._client = client
        self._mesures = mesures or Mesures()
        self._executeur = ThreadPoolExecutor(max_workers=ouvriers)
        self._en_cours: dict[int, _Reflexion] = {}
        self._plans: dict[int, PlanJour] = {}
        self._retour_routine: set[int] = set()
        self.nb_reflexions = 0

    def description(self) -> dict:
        return {**asdict(self.configuration), "version_prompt": VERSION_PROMPT}

    def demarrer(self, simulation) -> None:
        self._simulation = simulation
        self._ordonnanceur = Ordonnanceur(
            self.configuration.quota_agents,
            self.configuration.periode_ticks,
            simulation.alea.flux("cerveau/ordonnanceur"),
        )
        self._memoires = {
            agent.identifiant: Memoire(self.configuration.taille_memoire)
            for agent in simulation.agents
        }
        self._lieux = {agent.identifiant: self._tirer_lieux(agent) for agent in simulation.agents}

    def _tirer_lieux(self, agent) -> dict[str, int]:
        noeuds = self._simulation.noeuds_loisir
        flux = self._simulation.alea.flux(f"agents/{agent.identifiant}/lieux")
        lieux = {LIEU_DOMICILE: agent.domicile, LIEU_TRAVAIL: agent.travail}
        for rang in range(1, self.configuration.lieux_connus + 1):
            lieux[f"loisir_{rang}"] = noeuds[int(flux.random() * len(noeuds))]
        return lieux

    def tour(self, tick: int) -> None:
        self._recevoir(tick)
        if self._ordonnanceur.est_tour_de_reflexion(tick):
            self._demander(tick)

    def _demander(self, tick: int) -> None:
        candidats = [
            agent.identifiant
            for agent in self._simulation.agents
            if agent.identifiant not in self._en_cours
        ]
        for identifiant in self._ordonnanceur.tirer(candidats):
            self._lancer_reflexion(identifiant, tick)

    def _lancer_reflexion(self, identifiant: int, tick: int) -> None:
        nom_flux = f"agents/{identifiant}/reflexion"
        graine = int(self._simulation.alea.flux(nom_flux).random() * 2**31)
        lieux = self._lieux[identifiant]
        configuration = self._simulation.configuration
        societe = self._simulation.societe
        contexte, attendus = None, {}
        if societe is not None:
            contexte = societe.contexte_agent(identifiant)
            attendus = societe.choix_attendus(identifiant)
            configuration = replace(
                configuration, prix_loisir_centimes=self._simulation.prix_loisir()
            )
        demande = DemandeModele(
            agent=identifiant,
            tick=tick,
            prompt=construire_prompt(
                self._simulation.percevoir(self._simulation.agents[identifiant]),
                lieux,
                self._memoires[identifiant],
                configuration,
                self.configuration,
                contexte,
            ),
            graine=graine,
            modele=self.configuration.modele,
            temperature=self.configuration.temperature,
            nb_jetons_max=self.configuration.nb_jetons_max,
            schema=ajouter_choix(schema_plan(lieux, self.configuration), attendus),
        )
        self.nb_reflexions += 1
        self._en_cours[identifiant] = _Reflexion(
            demande,
            self._executeur.submit(self._appeler, demande),
            tick + self.configuration.delai_ticks,
            nom_flux,
            attendus,
        )

    def _appeler(self, demande: DemandeModele) -> str:
        debut = self._mesures.chrono()
        try:
            return self._client.generer(demande)
        finally:
            self._mesures.noter_latence(
                demande.agent, demande.tick, self._mesures.chrono() - debut
            )

    def _recevoir(self, tick: int) -> None:
        echues = sorted(
            identifiant
            for identifiant, reflexion in self._en_cours.items()
            if reflexion.echeance == tick
        )
        for identifiant in echues:
            self._appliquer(identifiant, self._en_cours.pop(identifiant), tick)

    def _appliquer(self, identifiant: int, reflexion: _Reflexion, tick: int) -> None:
        debut = self._mesures.chrono()
        texte, erreur, etapes, choix = None, None, None, {}
        try:
            texte = reflexion.futur.result()
            etapes = analyser_plan(texte, self._lieux[identifiant], self.configuration)
            choix = analyser_choix(texte, reflexion.choix_attendus)
        except (ErreurModele, ReponseInvalide) as exception:
            erreur = str(exception)
            etapes = None
        self._mesures.noter_attente(identifiant, tick, self._mesures.chrono() - debut)
        if etapes is None:
            self._mesures.noter_repli()
            if self._plans.pop(identifiant, None) is not None:
                self._retour_routine.add(identifiant)
        else:
            self._plans[identifiant] = PlanJour(etapes, self._lieux[identifiant])
            self._retour_routine.discard(identifiant)
            if self._simulation.societe is not None:
                self._simulation.societe.enregistrer_choix(identifiant, choix)
        demande = reflexion.demande
        evenement = {
            "type": "reflexion",
            "tick": tick,
            "tick_demande": demande.tick,
            "agent": identifiant,
            "graine": self._simulation.configuration.graine,
            "flux": reflexion.flux,
            "graine_modele": demande.graine,
            "modele": demande.modele,
            "version_prompt": VERSION_PROMPT,
            "contexte": demande.prompt,
            "reponse_brute": texte,
            "erreur": erreur,
            "source": SOURCE_REGLES if etapes is None else SOURCE_LLM,
            "plan": None if etapes is None else [asdict(etape) for etape in etapes],
        }
        if self._simulation.societe is not None:
            evenement["choix"] = choix
        self._simulation.journal.ecrire(evenement)

    def decider(self, perception: Perception, flux: Random) -> tuple[Intention, str]:
        identifiant = perception.agent
        plan = self._plans.get(identifiant)
        if plan is not None:
            intention = plan.prochaine_intention(perception, self._simulation.prix_loisir())
            if intention is not None:
                return intention, SOURCE_LLM
            del self._plans[identifiant]
            self._retour_routine.add(identifiant)
        if identifiant in self._retour_routine:
            self._retour_routine.discard(identifiant)
            if perception.noeud != perception.domicile:
                return Aller(perception.domicile, DOMICILE), SOURCE_REGLES
            perception = replace(perception, etape=PREFIXE_ARRIVEE + DOMICILE)
        return self._simulation.decideur.decider(perception, flux), SOURCE_REGLES

    def observer(self, evenement: dict) -> None:
        memoire = self._memoires[evenement["agent"]]
        heure = heure_lisible(self._seconde_du_jour(evenement["tick"]))
        if evenement["type"] == "arrivee":
            lieu = evenement["etape"].removeprefix(PREFIXE_ARRIVEE)
            memoire.retenir(f"{heure} : arrivé ({lieu})")
        elif evenement["intention"]["type"] == "Activite":
            nature = evenement["intention"]["nature"]
            minutes = evenement["intention"]["duree_s"] // 60
            memoire.retenir(f"{heure} : {nature} pendant {minutes} min")
            memoire.compter(nature)

    def _seconde_du_jour(self, tick: int) -> int:
        configuration = self._simulation.configuration
        secondes = configuration.heure_depart_s + tick * configuration.duree_tick_s
        return secondes % SECONDES_PAR_JOUR

    def fermer(self) -> None:
        self._executeur.shutdown(wait=True, cancel_futures=True)
