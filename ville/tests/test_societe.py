import io
import json
import os
import subprocess
import sys

import pytest

from ville.cerveau.client import ClientFactice
from ville.cerveau.decideur import CerveauLLM
from ville.cerveau.rejeu import ClientRejeu
from ville.cerveau.reponses import ReponseInvalide, ajouter_choix, analyser_choix
from ville.configuration import Configuration, ConfigurationCerveau, ConfigurationSociete
from ville.donnees.journal import Journal
from ville.moteur.agent import Activite, Agent
from ville.moteur.alea import SourceAlea
from ville.moteur.carte import Carte
from ville.moteur.simulation import Simulation
from ville.societe.economie import Economie
from ville.societe.election import Candidat, Election
from ville.societe.relations import SCORE_MAX, SCORE_MIN, Relations
from ville.societe.rencontres import DetecteurRencontres, en_metres, paires_proches
from ville.societe.rumeurs import Rumeurs
from ville.societe.scenarios import ScenarioInvalide, charger_scenario, valider_scenario
from ville.societe.societe import Societe
from ville.tests.conftest import donnees_grille

REGLAGES = ConfigurationSociete(nb_commerces=3)
CONFIGURATION = Configuration(
    nb_agents=20,
    salaire_horaire_centimes=REGLAGES.salaire_horaire_centimes,
    probabilite_loisir=REGLAGES.probabilite_loisir,
)


def agent(identifiant=0, budget=1000, noeud=1):
    return Agent(
        identifiant=identifiant,
        domicile=noeud,
        travail=2,
        vitesse_m_s=1.4,
        heure_travail_s=0,
        budget_centimes=budget,
        noeud=noeud,
    )


class JournalMemoire:
    def __init__(self):
        self.evenements = []

    def ecrire(self, evenement):
        self.evenements.append(evenement)

    def du_type(self, nature):
        return [e for e in self.evenements if e["type"] == nature]


def simuler(
    carte, heures=24.0, scenario=None, configuration=CONFIGURATION, reglages=REGLAGES, journal=None, **options
):
    journal = journal or JournalMemoire()
    societe = Societe(reglages, scenario)
    simulation = Simulation(configuration, carte, journal, societe=societe, **options)
    for _ in range(int(heures * 3600 / configuration.duree_tick_s)):
        simulation.avancer()
    return simulation, societe, journal


def test_salaire_preleve_sur_la_tresorerie():
    economie = Economie(REGLAGES, [1])
    employe = agent()
    avant = economie.monnaie_totale([employe])
    evenement = economie.payer_salaire(employe, 1200, 8 * 3600)
    assert employe.budget_centimes == 2200
    assert economie.commerces[0].tresorerie_centimes == REGLAGES.tresorerie_initiale_centimes - 1200
    assert economie.monnaie_totale([employe]) == avant
    assert evenement["verse_centimes"] == 1200
    assert economie.commerces[0].stock_milliemes == REGLAGES.stock_initial_milliemes + 880


def test_salaire_limite_par_la_tresorerie():
    economie = Economie(REGLAGES, [1])
    economie.commerces[0].tresorerie_centimes = 500
    employe = agent()
    assert economie.payer_salaire(employe, 1200, 3600)["verse_centimes"] == 500
    assert economie.commerces[0].tresorerie_centimes == 0
    assert employe.budget_centimes == 1500


def test_achat_transfere_l_argent_et_le_stock():
    economie = Economie(REGLAGES, [1])
    client, commerce = agent(), economie.commerces[0]
    avant = economie.monnaie_totale([client])
    assert economie.acheter(client, commerce)["refus"] is None
    assert client.budget_centimes == 0
    assert commerce.tresorerie_centimes == REGLAGES.tresorerie_initiale_centimes + 1000
    assert commerce.stock_milliemes == REGLAGES.stock_initial_milliemes - 1000
    assert economie.monnaie_totale([client]) == avant


def test_achat_refuse_sans_argent():
    economie = Economie(REGLAGES, [1])
    client = agent(budget=999)
    assert economie.acheter(client, economie.commerces[0])["refus"] == "budget"
    assert client.budget_centimes == 999


def test_achat_refuse_en_rupture():
    economie = Economie(REGLAGES, [1])
    economie.commerces[0].stock_milliemes = 999
    client = agent()
    assert economie.acheter(client, economie.commerces[0])["refus"] == "rupture"
    assert client.budget_centimes == 1000


def test_stock_bas_fait_monter_le_prix():
    economie = Economie(REGLAGES, [1])
    economie.commerces[0].stock_milliemes = 17999
    assert economie.ajuster_prix()[0]["nouveau_centimes"] == 1010


def test_stock_haut_fait_baisser_le_prix():
    economie = Economie(REGLAGES, [1])
    economie.commerces[0].stock_milliemes = 22001
    assert economie.ajuster_prix()[0]["nouveau_centimes"] == 990


@pytest.mark.parametrize("stock", [18000, 20000, 22000])
def test_stock_dans_la_tolerance_laisse_le_prix(stock):
    economie = Economie(REGLAGES, [1])
    economie.commerces[0].stock_milliemes = stock
    assert economie.ajuster_prix() == []


def test_les_prix_restent_contenus_sur_une_semaine(carte_grille):
    _, societe, journal = simuler(carte_grille, heures=7 * 24)
    assert journal.du_type("prix")
    for evenement in journal.du_type("prix"):
        assert abs(evenement["nouveau_centimes"] - evenement["ancien_centimes"]) <= max(
            1, evenement["ancien_centimes"] // 100
        )
    assert all(500 <= c.prix_centimes <= 2000 for c in societe.economie.commerces)


def test_prix_jamais_sous_le_minimum():
    economie = Economie(REGLAGES, [1])
    commerce = economie.commerces[0]
    commerce.stock_milliemes = 22001
    commerce.prix_centimes = REGLAGES.prix_min_centimes
    assert economie.ajuster_prix() == []
    assert commerce.prix_centimes == REGLAGES.prix_min_centimes


def test_petit_prix_bouge_quand_meme():
    economie = Economie(ConfigurationSociete(prix_initial_centimes=10, stock_initial_milliemes=0), [1])
    assert economie.ajuster_prix()[0]["nouveau_centimes"] == 11


def test_impot_et_redistribution_conservent_la_monnaie():
    economie = Economie(REGLAGES, [1])
    economie.taux_impot_pourcent = 25
    agents = [agent(i) for i in range(3)]
    avant = economie.monnaie_totale(agents)
    evenement = economie.payer_salaire(agents[0], 1000, 3600)
    assert evenement["impot_centimes"] == 250
    assert economie.caisse_centimes == 250
    assert economie.redistribuer(agents)["part_centimes"] == 83
    assert economie.caisse_centimes == 1
    assert economie.monnaie_totale(agents) == avant


def test_redistribution_sans_caisse():
    assert Economie(REGLAGES, [1]).redistribuer([agent()]) is None


def test_la_monnaie_est_conservee_sur_plusieurs_jours(carte_grille):
    simulation, societe, journal = simuler(carte_grille, heures=5 * 24)
    assert journal.du_type("salaire")
    assert journal.du_type("achat")
    assert societe.economie.monnaie_totale(simulation.agents) == societe.monnaie_initiale
    assert all(a.budget_centimes >= 0 for a in simulation.agents)
    assert all(c.tresorerie_centimes >= 0 for c in societe.economie.commerces)
    assert all(c.stock_milliemes >= 0 for c in societe.economie.commerces)


def test_rupture_de_stock_en_simulation(carte_grille):
    reglages = ConfigurationSociete(nb_commerces=3, stock_initial_milliemes=1000, production_horaire_milliemes=0)
    _, societe, journal = simuler(carte_grille, heures=30, reglages=reglages)
    refus = [e["refus"] for e in journal.du_type("achat")]
    assert "rupture" in refus
    assert refus.count(None) <= 3


def test_les_prix_reagissent_a_la_penurie(carte_grille):
    reglages = ConfigurationSociete(nb_commerces=3, production_horaire_milliemes=0, stock_initial_milliemes=5000)
    _, societe, journal = simuler(carte_grille, heures=48, reglages=reglages)
    assert journal.du_type("prix")
    assert all(c.prix_centimes > reglages.prix_initial_centimes for c in societe.economie.commerces)


def test_les_loisirs_des_regles_vont_dans_les_commerces(carte_grille):
    _, societe, journal = simuler(carte_grille)
    destinations = {
        e["noeud"] for e in journal.du_type("arrivee") if e["etape"] == "arrivee_loisir"
    }
    assert destinations
    assert destinations <= set(societe.noeuds_commerces)


def test_commerces_sur_des_noeuds_distincts_et_reproductibles(carte_grille):
    _, premiere, _ = simuler(carte_grille, heures=0)
    _, seconde, _ = simuler(carte_grille, heures=0)
    assert premiere.noeuds_commerces == seconde.noeuds_commerces
    assert len(set(premiere.noeuds_commerces)) == 3


def test_trop_de_commerces_refuse(carte_grille):
    with pytest.raises(ValueError, match="commerces"):
        simuler(carte_grille, heures=0, reglages=ConfigurationSociete(nb_commerces=7))


def test_paires_proches_identiques_a_une_recherche_exhaustive():
    tirage = SourceAlea(3).flux("essai")
    positions = {i: (tirage.random() * 300 - 150, tirage.random() * 300 - 150) for i in range(200)}
    attendu = sorted(
        (a, b)
        for a in positions
        for b in positions
        if a < b
        and (positions[a][0] - positions[b][0]) ** 2 + (positions[a][1] - positions[b][1]) ** 2 <= 15**2
    )
    assert attendu
    assert paires_proches(positions, 15.0) == attendu


def test_paires_a_la_limite_du_rayon():
    assert paires_proches({1: (0.0, 0.0), 2: (15.0, 0.0)}, 15.0) == [(1, 2)]
    assert paires_proches({1: (0.0, 0.0), 2: (15.1, 0.0)}, 15.0) == []


def test_une_rencontre_n_est_comptee_qu_a_l_arrivee_en_contact():
    detecteur = DetecteurRencontres(15.0)
    proches = {1: (0.0, 0.0), 2: (1.0, 0.0)}
    loin = {1: (0.0, 0.0), 2: (500.0, 0.0)}
    assert detecteur.actualiser(proches) == [(1, 2)]
    assert detecteur.actualiser(proches) == []
    assert detecteur.actualiser(loin) == []
    assert detecteur.actualiser(proches) == [(1, 2)]


def test_conversion_en_metres():
    x_a, y_a = en_metres(45.0, 4.0, 45.0)
    x_b, y_b = en_metres(45.001, 4.0, 45.0)
    assert x_a == x_b
    assert y_b - y_a == pytest.approx(111.132, abs=0.01)


def test_relation_symetrique_et_bornee():
    relations = Relations()
    relations.modifier(1, 2, 5)
    assert relations.score(2, 1) == 5
    assert relations.modifier(1, 2, 1000) == SCORE_MAX
    assert relations.modifier(2, 1, -5000) == SCORE_MIN


def test_relation_avec_soi_refusee():
    with pytest.raises(ValueError):
        Relations().modifier(1, 1, 1)


def test_meilleures_relations_triees():
    relations = Relations()
    relations.modifier(1, 3, 5)
    relations.modifier(1, 2, 5)
    relations.modifier(4, 1, 9)
    relations.modifier(2, 3, 50)
    assert relations.meilleures(1, 2) == [(4, 9), (2, 5)]


def test_rencontres_en_simulation_creent_des_relations(carte_grille):
    _, societe, journal = simuler(carte_grille, heures=12)
    rencontres = journal.du_type("rencontre")
    assert rencontres
    assert societe.nb_rencontres == len(rencontres)
    assert all(e["a"] < e["b"] for e in rencontres)
    dernier = rencontres[-1]
    assert societe.relations.score(dernier["a"], dernier["b"]) == dernier["score"] > 0


def transmettre(rumeurs, a, b, volonte=None):
    flux = SourceAlea(1).flux("essai")
    return rumeurs.transmettre(a, b, 5, volonte or (lambda agent: None), lambda rumeur: flux)


def test_rumeur_transmise_du_conteur_a_l_auditeur():
    rumeurs = Rumeurs(1.0)
    rumeurs.injecter("le pont ferme", 1, 0)
    evenements = transmettre(rumeurs, 2, 1)
    assert [(e["de"], e["a"]) for e in evenements] == [(1, 2)]
    assert [r.contenu for r in rumeurs.connues_par(2)] == ["le pont ferme"]


def test_rumeur_non_transmise_entre_ignorants_ou_initiés():
    rumeurs = Rumeurs(1.0)
    rumeurs.injecter("x", 1, 0)
    assert transmettre(rumeurs, 2, 3) == []
    transmettre(rumeurs, 1, 2)
    assert transmettre(rumeurs, 1, 2) == []


def test_probabilite_nulle_bloque_la_transmission():
    rumeurs = Rumeurs(0.0)
    rumeurs.injecter("x", 1, 0)
    assert transmettre(rumeurs, 1, 2) == []


def test_refus_du_modele_bloque_meme_a_probabilite_un():
    rumeurs = Rumeurs(1.0)
    rumeurs.injecter("x", 1, 0)
    assert transmettre(rumeurs, 1, 2, lambda agent: False) == []


def test_accord_du_modele_transmet_meme_a_probabilite_nulle():
    rumeurs = Rumeurs(0.0)
    rumeurs.injecter("x", 1, 0)
    assert transmettre(rumeurs, 1, 2, lambda agent: True)[0]["decidee_par_le_modele"] is True


def carte_deux_quartiers() -> Carte:
    noeuds, aretes = [], []
    for base, longitude in ((1, 4.0), (11, 5.0)):
        for rang in range(4):
            noeuds.append({"id": base + rang, "lat": 45.0 + rang * 0.001, "lon": longitude})
        for rang in range(3):
            for origine, destination in ((base + rang, base + rang + 1), (base + rang + 1, base + rang)):
                aretes.append({"origine": origine, "destination": destination, "longueur": 100.0})
    for origine, destination in ((4, 11), (11, 4)):
        aretes.append({"origine": origine, "destination": destination, "longueur": 80000.0})
    return Carte({"noeuds": noeuds, "aretes": aretes})


class DecideurSurPlace:
    def decider(self, perception, flux):
        return Activite("attente", 3600)


def test_rumeur_se_propage_de_proche_en_proche(carte_grille):
    reglages = ConfigurationSociete(nb_commerces=3, probabilite_transmission=1.0)
    scenario = [{"tick": 0, "type": "rumeur", "contenu": "le pont ferme", "source": 0}]
    _, societe, journal = simuler(carte_grille, scenario=scenario, reglages=reglages)
    connaisseurs = societe.rumeurs.rumeurs[0].apprise_par
    assert len(connaisseurs) > 5
    assert connaisseurs[0] == 0
    transmissions = journal.du_type("rumeur_transmise")
    assert len(transmissions) == len(connaisseurs) - 1
    assert any(e["de"] != 0 for e in transmissions)


def test_rumeur_ne_franchit_pas_deux_groupes_qui_ne_se_croisent_pas():
    carte = carte_deux_quartiers()
    reglages = ConfigurationSociete(nb_commerces=2, probabilite_transmission=1.0)
    scenario = [{"tick": 0, "type": "rumeur", "contenu": "x", "source": 0}]
    societe = Societe(reglages, scenario)
    simulation = Simulation(
        Configuration(nb_agents=20), carte, JournalMemoire(), decideur=None, societe=societe
    )
    for numero, sujet in enumerate(simulation.agents):
        sujet.noeud = sujet.domicile = 1 + numero % 4 if numero < 10 else 11 + numero % 4
    simulation.decideur = DecideurSurPlace()
    for _ in range(100):
        simulation.avancer()
    connaisseurs = set(societe.rumeurs.rumeurs[0].apprise_par)
    assert len(connaisseurs) > 1
    assert connaisseurs <= set(range(10))


def election(tick_vote=10):
    return Election([Candidat(1, 10), Candidat(2, 40)], tick_vote)


def depouiller(scrutin, votants, relations=None):
    alea = SourceAlea(1)
    return scrutin.depouiller(
        votants,
        relations or Relations(),
        lambda votant: alea.flux(f"v/{votant}"),
        alea.flux("egalite"),
    )


def test_votes_exprimes_prioritaires():
    scrutin = election()
    for votant in (3, 4, 5):
        scrutin.enregistrer_vote(votant, "habitant_2")
    elu, resultat = depouiller(scrutin, [1, 2, 3, 4, 5])
    assert elu.agent == 2
    assert resultat["bulletins"] == {"1": 1, "2": 4}
    assert resultat["votes_du_modele"] == 3


def test_les_regles_votent_pour_la_meilleure_relation():
    relations = Relations()
    for votant in range(3, 8):
        relations.modifier(votant, 1, 5)
    elu, resultat = depouiller(election(), list(range(1, 8)), relations)
    assert elu.agent == 1
    assert resultat["bulletins"] == {"1": 6, "2": 1}
    assert resultat["egalite"] is False


def test_egalite_departagee_de_facon_reproductible():
    premier = depouiller(election(), [1, 2])
    second = depouiller(election(), [1, 2])
    assert premier[1]["egalite"] is True
    assert premier == second


def test_candidat_inconnu_refuse():
    with pytest.raises(ValueError, match="candidat inconnu"):
        election().enregistrer_vote(3, "habitant_9")


@pytest.mark.parametrize("candidats", [[Candidat(1, 1)], [Candidat(1, 1), Candidat(1, 2)]])
def test_election_invalide_refusee(candidats):
    with pytest.raises(ValueError):
        Election(candidats, 5)


SCENARIO_ELECTION = [
    {
        "tick": 0,
        "type": "election",
        "tick_vote": 100,
        "candidats": [
            {"agent": 0, "taux_impot_pourcent": 10},
            {"agent": 1, "taux_impot_pourcent": 40},
        ],
    }
]


def test_election_truquee_par_scenario_donne_le_gagnant_attendu_et_change_l_impot(carte_grille):
    societe = Societe(REGLAGES, SCENARIO_ELECTION)
    journal = JournalMemoire()
    simulation = Simulation(CONFIGURATION, carte_grille, journal, societe=societe)
    for votant in range(2, 20):
        societe.relations.modifier(votant, 1, 50)
    for _ in range(200):
        simulation.avancer()
    assert journal.du_type("election_ouverte")
    resultat = journal.du_type("election_resultat")[0]
    assert resultat["elu"] == 1
    assert resultat["bulletins"]["1"] >= 19
    assert societe.economie.taux_impot_pourcent == 40
    assert societe.election is None


def test_l_impot_change_les_budgets_sans_changer_le_total(carte_grille):
    scenario = [
        {
            "tick": 0,
            "type": "election",
            "tick_vote": 1,
            "candidats": [
                {"agent": 0, "taux_impot_pourcent": 50},
                {"agent": 1, "taux_impot_pourcent": 50},
            ],
        }
    ]
    simulation, societe, journal = simuler(carte_grille, heures=3 * 24, scenario=scenario)
    salaires = journal.du_type("salaire")
    assert any(e["impot_centimes"] > 0 for e in salaires)
    assert journal.du_type("redistribution")
    assert societe.economie.monnaie_totale(simulation.agents) == societe.monnaie_initiale


def test_pluie_d_argent_mesuree(carte_grille):
    scenario = [{"tick": 10, "type": "pluie_argent", "montant_centimes": 500}]
    simulation, societe, journal = simuler(carte_grille, heures=48, scenario=scenario)
    assert journal.du_type("pluie_argent")[0]["tick"] == 10
    assert societe.economie.monnaie_injectee_centimes == 500 * 20
    total = societe.economie.monnaie_totale(simulation.agents)
    assert total == societe.monnaie_initiale + 500 * 20


@pytest.mark.parametrize(
    "evenement",
    [
        "pas un objet",
        {"type": "pluie_argent", "montant_centimes": 1},
        {"tick": -1, "type": "pluie_argent", "montant_centimes": 1},
        {"tick": 0, "type": "pluie_argent", "montant_centimes": 1.5},
        {"tick": 0, "type": "inconnu"},
        {"tick": 0, "type": "rumeur", "contenu": "", "source": 0},
        {"tick": 0, "type": "rumeur", "contenu": "x", "source": 99},
        {"tick": 5, "type": "election", "tick_vote": 5, "candidats": []},
        {"tick": 0, "type": "election", "tick_vote": 5, "candidats": [{"agent": 0, "taux_impot_pourcent": 1}]},
        {"tick": 0, "type": "election", "tick_vote": 5, "candidats": [{"agent": 0, "taux_impot_pourcent": 1}, {"agent": 99, "taux_impot_pourcent": 1}]},
        {"tick": 0, "type": "election", "tick_vote": 5, "candidats": [{"agent": 0, "taux_impot_pourcent": 101}, {"agent": 1, "taux_impot_pourcent": 1}]},
    ],
)
def test_scenario_invalide_refuse(evenement):
    with pytest.raises(ScenarioInvalide):
        valider_scenario([evenement], 20)


def test_scenario_trie_et_chargement(tmp_path):
    chemin = tmp_path / "s.json"
    evenements = [
        {"tick": 9, "type": "pluie_argent", "montant_centimes": 1},
        {"tick": 2, "type": "pluie_argent", "montant_centimes": 2},
    ]
    chemin.write_text(json.dumps(evenements), encoding="utf-8")
    assert [e["tick"] for e in valider_scenario(charger_scenario(chemin), 5)] == [2, 9]
    chemin.write_text("{}", encoding="utf-8")
    with pytest.raises(ScenarioInvalide):
        charger_scenario(chemin)


def test_ajouter_et_analyser_les_choix():
    attendus = {"repeter_rumeurs": None, "vote": ["habitant_1", "habitant_2"]}
    schema = ajouter_choix({"type": "object", "properties": {"etapes": {}}, "required": ["etapes"]}, attendus)
    assert schema["required"] == ["etapes", "repeter_rumeurs", "vote"]
    assert schema["properties"]["repeter_rumeurs"] == {"type": "boolean"}
    assert schema["properties"]["vote"]["enum"] == ["habitant_1", "habitant_2"]
    texte = json.dumps({"etapes": [], "repeter_rumeurs": False, "vote": "habitant_2"})
    assert analyser_choix(texte, attendus) == {"repeter_rumeurs": False, "vote": "habitant_2"}


def test_sans_choix_attendu_le_schema_ne_change_pas():
    schema = {"type": "object", "properties": {}, "required": []}
    assert ajouter_choix(schema, {}) is schema
    assert analyser_choix("{}", {}) == {}


@pytest.mark.parametrize(
    "contenu",
    [
        {},
        {"repeter_rumeurs": "oui", "vote": "habitant_1"},
        {"repeter_rumeurs": 1, "vote": "habitant_1"},
        {"repeter_rumeurs": True, "vote": "habitant_9"},
        {"repeter_rumeurs": True},
    ],
)
def test_choix_invalides(contenu):
    attendus = {"repeter_rumeurs": None, "vote": ["habitant_1"]}
    with pytest.raises(ReponseInvalide):
        analyser_choix(json.dumps(contenu), attendus)


def plan_societal(demande) -> str:
    proprietes = demande.schema["properties"]
    plan = {"etapes": [{"lieu": "loisir_1", "activite": "loisir", "duree_minutes": 5}]}
    if "repeter_rumeurs" in proprietes:
        plan["repeter_rumeurs"] = True
    if "vote" in proprietes:
        plan["vote"] = proprietes["vote"]["enum"][-1]
    return json.dumps(plan)


SCENARIO_COMPLET = [
    {"tick": 0, "type": "rumeur", "contenu": "le pont ferme", "source": 0},
    {"tick": 2, "type": "pluie_argent", "montant_centimes": 100},
    {
        "tick": 3,
        "type": "election",
        "tick_vote": 200,
        "candidats": [
            {"agent": 0, "taux_impot_pourcent": 10},
            {"agent": 1, "taux_impot_pourcent": 30},
        ],
    },
]


def simuler_avec_cerveau(carte, client, ticks=400, scenario=SCENARIO_COMPLET):
    sortie = io.StringIO()
    cerveau = CerveauLLM(ConfigurationCerveau(), client)
    societe = Societe(REGLAGES, scenario)
    simulation = Simulation(
        CONFIGURATION, carte, Journal(sortie), cerveau=cerveau, societe=societe
    )
    for _ in range(ticks):
        simulation.avancer()
    cerveau.fermer()
    return sortie.getvalue(), simulation, societe


def lire(contenu):
    return [json.loads(ligne) for ligne in contenu.splitlines()]


def test_le_cerveau_recoit_le_contexte_et_le_schema_de_la_societe(carte_grille):
    client = ClientFactice(plan_societal)
    _, _, _ = simuler_avec_cerveau(carte_grille, client)
    avec_vote = [d for d in client.demandes if "vote" in d.schema["properties"]]
    assert avec_vote
    assert all("Élection en cours" in d.prompt for d in avec_vote)
    assert all("Impôt actuel" in d.prompt for d in client.demandes)
    sources = [d for d in client.demandes if d.agent == 0 and d.tick >= 6]
    assert any("le pont ferme" in d.prompt for d in sources)


def test_les_votes_du_modele_decident_de_l_election(carte_grille):
    contenu, _, societe = simuler_avec_cerveau(carte_grille, ClientFactice(plan_societal))
    resultat = [e for e in lire(contenu) if e["type"] == "election_resultat"][0]
    assert resultat["votes_du_modele"] > 0
    assert resultat["elu"] == 1
    assert societe.economie.taux_impot_pourcent == 30


def test_la_volonte_du_modele_decide_de_la_rumeur(carte_grille):
    contenu, _, _ = simuler_avec_cerveau(carte_grille, ClientFactice(plan_societal), ticks=2000)
    transmissions = [e for e in lire(contenu) if e["type"] == "rumeur_transmise"]
    assert any(e["decidee_par_le_modele"] for e in transmissions)


def test_un_choix_societal_invalide_donne_un_repli_journalise(carte_grille):
    def vote_invalide(demande):
        plan = json.loads(plan_societal(demande))
        if "vote" in plan:
            plan["vote"] = "personne"
        return json.dumps(plan)

    contenu, _, _ = simuler_avec_cerveau(carte_grille, ClientFactice(vote_invalide))
    lignes = [e for e in lire(contenu) if e["type"] == "reflexion" and e["erreur"]]
    assert lignes
    assert all("vote" in e["erreur"] and e["plan"] is None for e in lignes)
    assert all(e["source"] == "regles" for e in lignes)
    resultat = [e for e in lire(contenu) if e["type"] == "election_resultat"][0]
    assert resultat["votes_du_modele"] == 0


def test_la_latence_ne_change_pas_le_journal_de_la_societe(carte_grille):
    rapide, _, _ = simuler_avec_cerveau(carte_grille, ClientFactice(plan_societal))
    lent, _, _ = simuler_avec_cerveau(carte_grille, ClientFactice(plan_societal, latence_s=0.002))
    assert rapide == lent


def test_rejeu_identique_avec_la_societe(carte_grille, tmp_path):
    original, _, _ = simuler_avec_cerveau(carte_grille, ClientFactice(plan_societal))
    chemin = tmp_path / "o.jsonl"
    chemin.write_text(original, encoding="utf-8", newline="\n")
    rejoue, _, _ = simuler_avec_cerveau(carte_grille, ClientRejeu(chemin))
    assert rejoue == original


def test_la_monnaie_est_conservee_avec_le_cerveau(carte_grille):
    _, simulation, societe = simuler_avec_cerveau(carte_grille, ClientFactice(plan_societal), ticks=2000)
    assert societe.economie.monnaie_totale(simulation.agents) == (
        societe.monnaie_initiale + societe.economie.monnaie_injectee_centimes
    )


def executer_cli(*arguments, hash_seed="0"):
    return subprocess.run(
        [sys.executable, "-m", "ville.moteur", *map(str, arguments)],
        env={**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.fixture
def fichiers(tmp_path):
    carte = tmp_path / "carte.json"
    carte.write_text(json.dumps(donnees_grille()), encoding="utf-8")
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps(SCENARIO_COMPLET), encoding="utf-8")
    return carte, scenario


def test_societe_sans_cerveau_identique_a_l_octet_entre_processus(fichiers, tmp_path):
    carte, scenario = fichiers
    communs = ("--carte", carte, "--heures", 24, "--agents", 30, "--societe", "--scenario", scenario)
    premier = executer_cli(*communs, "--journal", tmp_path / "a.jsonl", hash_seed="1")
    second = executer_cli(*communs, "--journal", tmp_path / "b.jsonl", hash_seed="98765")
    assert premier.returncode == 0, premier.stderr
    assert second.returncode == 0, second.stderr
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()
    assert "monnaie :" in premier.stdout


def test_ligne_de_commande_rejeu_avec_la_societe(fichiers, tmp_path):
    carte, _ = fichiers
    chemin_carte = Carte.charger(carte)
    original, _, _ = simuler_avec_cerveau(chemin_carte, ClientFactice(plan_societal), ticks=360)
    premier = tmp_path / "a.jsonl"
    premier.write_text(original, encoding="utf-8", newline="\n")
    second = tmp_path / "b.jsonl"
    resultat = executer_cli(
        "--carte", carte, "--heures", 1, "--rejeu", premier, "--journal", second, hash_seed="5"
    )
    assert resultat.returncode == 0, resultat.stderr
    assert second.read_bytes() == premier.read_bytes()


def test_ligne_de_commande_scenario_invalide(fichiers, tmp_path):
    carte, scenario = fichiers
    scenario.write_text('[{"tick": 0, "type": "inconnu"}]', encoding="utf-8")
    resultat = executer_cli(
        "--carte", carte, "--heures", 0.01, "--agents", 3, "--societe", "--scenario", scenario,
        "--journal", tmp_path / "a.jsonl",
    )
    assert resultat.returncode == 4
    assert "scénario invalide" in resultat.stderr


def test_societe_absente_ne_change_pas_le_journal(carte_grille):
    def journal_de(**options):
        sortie = io.StringIO()
        simulation = Simulation(Configuration(nb_agents=10), carte_grille, Journal(sortie), **options)
        for _ in range(500):
            simulation.avancer()
        return sortie.getvalue()

    assert journal_de() == journal_de(societe=None)
    assert '"type":"rencontre"' not in journal_de()
