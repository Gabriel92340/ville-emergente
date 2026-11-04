from dataclasses import dataclass

from ville.configuration import ConfigurationSociete
from ville.moteur.agent import Agent

MILLIEMES_PAR_UNITE = 1000


@dataclass
class Commerce:
    identifiant: int
    noeud: int
    tresorerie_centimes: int
    stock_milliemes: int
    prix_centimes: int


class Economie:
    def __init__(self, configuration: ConfigurationSociete, noeuds: list[int]):
        self._configuration = configuration
        self.commerces = [
            Commerce(
                rang,
                noeud,
                configuration.tresorerie_initiale_centimes,
                configuration.stock_initial_milliemes,
                configuration.prix_initial_centimes,
            )
            for rang, noeud in enumerate(noeuds)
        ]
        self._par_noeud = {commerce.noeud: commerce for commerce in self.commerces}
        self.caisse_centimes = 0
        self.taux_impot_pourcent = configuration.taux_impot_initial_pourcent
        self.monnaie_injectee_centimes = 0

    def employeur_de(self, agent: Agent) -> Commerce:
        return self.commerces[agent.identifiant % len(self.commerces)]

    def commerce_au_noeud(self, noeud: int) -> Commerce | None:
        return self._par_noeud.get(noeud)

    def prix_moyen(self) -> int:
        return sum(commerce.prix_centimes for commerce in self.commerces) // len(self.commerces)

    def monnaie_totale(self, agents: list[Agent]) -> int:
        return (
            sum(agent.budget_centimes for agent in agents)
            + sum(commerce.tresorerie_centimes for commerce in self.commerces)
            + self.caisse_centimes
        )

    def payer_salaire(self, agent: Agent, salaire_du: int, duree_s: int) -> dict:
        commerce = self.employeur_de(agent)
        verse = min(salaire_du, commerce.tresorerie_centimes)
        impot = verse * self.taux_impot_pourcent // 100
        commerce.tresorerie_centimes -= verse
        agent.budget_centimes += verse - impot
        self.caisse_centimes += impot
        production = self._configuration.production_horaire_milliemes * duree_s // 3600
        commerce.stock_milliemes += production
        return {
            "type": "salaire",
            "agent": agent.identifiant,
            "commerce": commerce.identifiant,
            "du_centimes": salaire_du,
            "verse_centimes": verse,
            "impot_centimes": impot,
            "production_milliemes": production,
        }

    def acheter(self, agent: Agent, commerce: Commerce) -> dict:
        prix = commerce.prix_centimes
        if commerce.stock_milliemes < MILLIEMES_PAR_UNITE:
            refus = "rupture"
        elif agent.budget_centimes < prix:
            refus = "budget"
        else:
            refus = None
            agent.budget_centimes -= prix
            commerce.tresorerie_centimes += prix
            commerce.stock_milliemes -= MILLIEMES_PAR_UNITE
        return {
            "type": "achat",
            "agent": agent.identifiant,
            "commerce": commerce.identifiant,
            "prix_centimes": prix,
            "refus": refus,
        }

    def ajuster_prix(self) -> list[dict]:
        evenements = []
        cible = self._configuration.stock_cible_milliemes
        marge = cible * self._configuration.tolerance_stock_pourcent // 100
        for commerce in self.commerces:
            pas = max(1, commerce.prix_centimes * self._configuration.pas_prix_pourcent // 100)
            ancien = commerce.prix_centimes
            if commerce.stock_milliemes < cible - marge:
                commerce.prix_centimes = ancien + pas
            elif commerce.stock_milliemes > cible + marge:
                commerce.prix_centimes = max(self._configuration.prix_min_centimes, ancien - pas)
            if commerce.prix_centimes != ancien:
                evenements.append(
                    {
                        "type": "prix",
                        "commerce": commerce.identifiant,
                        "ancien_centimes": ancien,
                        "nouveau_centimes": commerce.prix_centimes,
                        "stock_milliemes": commerce.stock_milliemes,
                    }
                )
        return evenements

    def redistribuer(self, agents: list[Agent]) -> dict | None:
        part = self.caisse_centimes // len(agents)
        if part == 0:
            return None
        for agent in agents:
            agent.budget_centimes += part
        self.caisse_centimes -= part * len(agents)
        return {"type": "redistribution", "part_centimes": part, "reste_centimes": self.caisse_centimes}

    def injecter(self, agents: list[Agent], montant_par_agent: int) -> dict:
        for agent in agents:
            agent.budget_centimes += montant_par_agent
        self.monnaie_injectee_centimes += montant_par_agent * len(agents)
        return {"type": "pluie_argent", "montant_par_agent_centimes": montant_par_agent}
