import hashlib
import io
import json
import os
import random
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

import ville
from ville.cerveau import banc
from ville.cerveau.client import ClientFactice, ErreurModele
from ville.cerveau.decideur import CerveauLLM
from ville.cerveau.memoire import Memoire
from ville.cerveau.plan import EtapePlan, PlanJour
from ville.cerveau.prompts import construire_prompt, euros, heure_lisible
from ville.cerveau.rejeu import ClientRejeu, RejeuDivergent
from ville.cerveau.reponses import ReponseInvalide, analyser_plan, schema_plan
from ville.configuration import Configuration, ConfigurationCerveau
from ville.donnees.journal import Journal
from ville.donnees.mesures import Mesures
from ville.moteur.agent import Activite, Aller, Perception
from ville.moteur.execution import Execution, photographier
from ville.moteur.simulation import Simulation
from ville.tests.conftest import donnees_grille

LIEUX = {"domicile": 1, "travail": 3, "loisir_1": 5}
CARTE_REELLE = Path(ville.__file__).parent / "cartes" / "lyon_presquile.json"
EMPREINTE_PHASE_1 = "fe80298b837946f98d731fbca3132fc80c47d867be16fbfadbc5ddba6f033fd9"


def perception(**champs) -> Perception:
    base = dict(
        tick=0,
        seconde_du_jour=8 * 3600,
        agent=0,
        noeud=1,
        etape="initial",
        budget_centimes=10000,
        domicile=1,
        travail=3,
        heure_travail_s=8 * 3600,
    )
    return Perception(**{**base, **champs})


def plan_selon_graine(demande) -> str:
    tirage = random.Random(demande.graine)
    variantes = demande.schema["properties"]["etapes"]["items"]["anyOf"]
    lieux = variantes[1]["properties"]["lieu"]["enum"]
    lieu = tirage.choice([nom for nom in lieux if nom.startswith("loisir")])
    return json.dumps(
        {
            "etapes": [
                {"lieu": lieu, "activite": "loisir", "duree_minutes": tirage.randint(1, 5)},
                {"lieu": "travail", "activite": "travail", "duree_minutes": 10},
            ]
        }
    )


def simuler(
    carte,
    client,
    ticks=120,
    configuration=None,
    cerveau_config=None,
    ouvriers=1,
    mesures=None,
):
    sortie = io.StringIO()
    cerveau = CerveauLLM(
        cerveau_config or ConfigurationCerveau(),
        client,
        ouvriers=ouvriers,
        mesures=mesures,
    )
    simulation = Simulation(
        configuration or Configuration(nb_agents=20),
        carte,
        Journal(sortie),
        cerveau=cerveau,
    )
    for _ in range(ticks):
        simulation.avancer()
    cerveau.fermer()
    return sortie.getvalue(), simulation, cerveau


def evenements(contenu: str, nature: str) -> list[dict]:
    lignes = (json.loads(ligne) for ligne in contenu.splitlines())
    return [ligne for ligne in lignes if ligne["type"] == nature]


def test_regles_seules_inchangees_a_l_octet_depuis_la_phase_1():
    from ville.moteur.carte import Carte

    sortie = io.StringIO()
    simulation = Simulation(Configuration(), Carte.charger(CARTE_REELLE), Journal(sortie))
    for _ in range(24 * 360):
        simulation.avancer()
    corps = sortie.getvalue().split("\n", 1)[1]
    assert hashlib.sha256(corps.encode("utf-8")).hexdigest() == EMPREINTE_PHASE_1


def test_reponse_appliquee_exactement_au_tick_prevu(carte_grille):
    contenu, _, _ = simuler(
        carte_grille, ClientFactice(plan_selon_graine), cerveau_config=ConfigurationCerveau(delai_ticks=7)
    )
    reflexions = evenements(contenu, "reflexion")
    assert reflexions
    assert all(ligne["tick"] == ligne["tick_demande"] + 7 for ligne in reflexions)


def test_la_latence_ne_change_pas_le_journal(carte_grille):
    rapide, _, _ = simuler(carte_grille, ClientFactice(plan_selon_graine))
    lent, _, _ = simuler(carte_grille, ClientFactice(plan_selon_graine, latence_s=0.01), ouvriers=3)
    assert rapide == lent


def test_latences_variables_dans_le_desordre_ne_changent_pas_le_journal(carte_grille):
    def desordonne(demande):
        time.sleep(((demande.agent * 7) % 5) * 0.004)
        return plan_selon_graine(demande)

    temoin, _, _ = simuler(carte_grille, ClientFactice(plan_selon_graine))
    agite, _, _ = simuler(carte_grille, ClientFactice(desordonne), ouvriers=4)
    assert temoin == agite


def test_la_simulation_attend_une_reponse_en_retard(carte_grille):
    mesures = Mesures()
    simuler(
        carte_grille,
        ClientFactice(plan_selon_graine, latence_s=0.05),
        ticks=8,
        cerveau_config=ConfigurationCerveau(quota_agents=1, delai_ticks=1),
        mesures=mesures,
    )
    assert sum(mesures.attentes_s) > 0.02


def test_budget_d_appels_respecte(carte_grille):
    client = ClientFactice(plan_selon_graine)
    contenu, _, cerveau = simuler(
        carte_grille,
        client,
        ticks=60,
        cerveau_config=ConfigurationCerveau(quota_agents=2, periode_ticks=6),
    )
    assert cerveau.nb_reflexions == 2 * 10
    assert len(client.demandes) <= cerveau.nb_reflexions
    par_tick = Counter(ligne["tick_demande"] for ligne in evenements(contenu, "reflexion"))
    assert par_tick == {tick: 2 for tick in range(0, 54, 6)}


def test_un_agent_ne_reflechit_pas_deux_fois_en_meme_temps(carte_grille):
    client = ClientFactice(plan_selon_graine)
    contenu, _, cerveau = simuler(
        carte_grille,
        client,
        ticks=30,
        configuration=Configuration(nb_agents=3),
        cerveau_config=ConfigurationCerveau(quota_agents=3, periode_ticks=2, delai_ticks=6),
    )
    assert cerveau.nb_reflexions == 15
    assert {ligne["tick_demande"] for ligne in evenements(contenu, "reflexion")} == {
        0,
        6,
        12,
        18,
    }


def test_agents_non_tires_suivent_les_regles(carte_grille):
    client = ClientFactice(plan_selon_graine)
    contenu, _, _ = simuler(
        carte_grille,
        client,
        ticks=2000,
        cerveau_config=ConfigurationCerveau(quota_agents=0),
    )
    decisions = evenements(contenu, "decision")
    assert decisions
    assert {ligne["source"] for ligne in decisions} == {"regles"}
    assert client.demandes == []


def test_le_plan_du_modele_est_execute_avec_la_bonne_source(carte_grille):
    contenu, _, _ = simuler(carte_grille, ClientFactice(plan_selon_graine), ticks=600)
    decisions = evenements(contenu, "decision")
    llm = [ligne for ligne in decisions if ligne["source"] == "llm"]
    assert llm
    assert {"Aller", "Activite"} >= {ligne["intention"]["type"] for ligne in llm}


def test_toute_reflexion_est_journalisee_avec_contexte_et_reponse(carte_grille):
    client = ClientFactice(plan_selon_graine)
    contenu, simulation, _ = simuler(carte_grille, client)
    entete = evenements(contenu, "entete")[0]
    assert entete["cerveau"]["modele"] == "qwen2.5:3b"
    assert entete["cerveau"]["version_prompt"]
    reflexions = evenements(contenu, "reflexion")
    assert reflexions
    for ligne in reflexions:
        assert ligne["graine"] == 42
        assert ligne["flux"] == f"agents/{ligne['agent']}/reflexion"
        assert ligne["contexte"].startswith("Tu es l'habitant")
        assert json.loads(ligne["reponse_brute"])["etapes"] == ligne["plan"]
        assert ligne["erreur"] is None
        assert ligne["source"] == "llm"


@pytest.mark.parametrize(
    "fonction",
    [
        lambda demande: "ce n'est pas du JSON",
        lambda demande: '{"etapes":[{"lieu":"lune","activite":"travail","duree_minutes":10}]}',
    ],
    ids=["non_json", "lieu_inconnu"],
)
def test_reponse_invalide_donne_un_repli_journalise(carte_grille, fonction):
    mesures = Mesures()
    contenu, simulation, _ = simuler(carte_grille, ClientFactice(fonction), mesures=mesures)
    reflexions = evenements(contenu, "reflexion")
    assert reflexions
    for ligne in reflexions:
        assert ligne["source"] == "regles"
        assert ligne["erreur"]
        assert ligne["plan"] is None
        assert ligne["reponse_brute"] is not None
    assert mesures.replis == len(reflexions)
    assert {ligne["source"] for ligne in evenements(contenu, "decision")} == {"regles"}


def test_panne_du_modele_donne_un_repli_journalise(carte_grille):
    def en_panne(demande):
        raise ErreurModele("délai dépassé")

    contenu, simulation, _ = simuler(carte_grille, ClientFactice(en_panne))
    reflexions = evenements(contenu, "reflexion")
    assert reflexions
    assert all(ligne["erreur"] == "délai dépassé" for ligne in reflexions)
    assert all(ligne["reponse_brute"] is None for ligne in reflexions)


def test_une_erreur_de_programmation_n_est_pas_masquee(carte_grille):
    def bogue(demande):
        raise KeyError("bogue")

    with pytest.raises(KeyError):
        simuler(carte_grille, ClientFactice(bogue))


def test_retour_a_la_routine_apres_un_plan(carte_grille):
    contenu, simulation, _ = simuler(
        carte_grille,
        ClientFactice(plan_selon_graine),
        ticks=48 * 360,
        cerveau_config=ConfigurationCerveau(quota_agents=1, periode_ticks=360, delai_ticks=6),
    )
    decisions = evenements(contenu, "decision")
    assert {"llm", "regles"} == {ligne["source"] for ligne in decisions}
    precedente = {}
    retours = 0
    for ligne in decisions:
        avant = precedente.get(ligne["agent"])
        if avant is not None and avant["source"] == "llm" and ligne["source"] == "regles":
            retours += 1
            contexte = ligne["contexte"]
            if contexte["noeud"] == contexte["domicile"]:
                assert ligne["intention"]["nature"] == "attente"
            else:
                assert ligne["intention"] == {
                    "type": "Aller",
                    "destination": contexte["domicile"],
                    "motif": "domicile",
                }
        precedente[ligne["agent"]] = ligne
    assert retours > 0
    for agent in simulation.agents:
        assert agent.budget_centimes >= 0
        assert agent.noeud in carte_grille.noeuds


def test_la_memoire_est_alimentee_et_entre_dans_les_prompts(carte_grille):
    client = ClientFactice(plan_selon_graine)
    simuler(
        carte_grille,
        client,
        ticks=4000,
        cerveau_config=ConfigurationCerveau(quota_agents=20, periode_ticks=1000),
    )
    tardifs = [demande for demande in client.demandes if demande.tick == 3000]
    assert tardifs
    assert any("arrivé" in demande.prompt for demande in tardifs)
    assert any("Compteurs : attente" in demande.prompt for demande in tardifs)


def test_rejeu_identique_a_l_octet(carte_grille, tmp_path):
    original, _, _ = simuler(carte_grille, ClientFactice(plan_selon_graine))
    chemin = tmp_path / "original.jsonl"
    chemin.write_text(original, encoding="utf-8", newline="\n")
    rejoue, _, _ = simuler(carte_grille, ClientRejeu(chemin))
    assert rejoue == original


def test_rejeu_identique_avec_erreurs_et_reponses_invalides(carte_grille, tmp_path):
    def mixte(demande):
        if demande.agent % 3 == 0:
            raise ErreurModele("panne")
        if demande.agent % 3 == 1:
            return "invalide"
        return plan_selon_graine(demande)

    original, _, _ = simuler(carte_grille, ClientFactice(mixte))
    chemin = tmp_path / "original.jsonl"
    chemin.write_text(original, encoding="utf-8", newline="\n")
    rejoue, _, _ = simuler(carte_grille, ClientRejeu(chemin))
    assert rejoue == original


def test_rejeu_divergent_refuse(carte_grille, tmp_path):
    original, _, _ = simuler(carte_grille, ClientFactice(plan_selon_graine))
    chemin = tmp_path / "original.jsonl"
    chemin.write_text(original, encoding="utf-8", newline="\n")
    with pytest.raises(RejeuDivergent):
        simuler(
            carte_grille,
            ClientRejeu(chemin),
            configuration=Configuration(nb_agents=20, graine=43),
        )


def test_instantane_immuable_et_lisible(carte_grille):
    _, simulation, _ = simuler(carte_grille, ClientFactice(plan_selon_graine), ticks=10)
    instantane = photographier(simulation)
    assert instantane.tick == 10
    assert len(instantane.agents) == 20
    with pytest.raises(AttributeError):
        instantane.tick = 3


def test_le_lecteur_a_10_hz_n_est_jamais_bloque_par_un_modele_lent(carte_grille):
    sortie = io.StringIO()
    cerveau = CerveauLLM(
        ConfigurationCerveau(quota_agents=5, periode_ticks=2, delai_ticks=1),
        ClientFactice(plan_selon_graine, latence_s=0.1),
    )
    simulation = Simulation(Configuration(nb_agents=100), carte_grille, Journal(sortie), cerveau=cerveau)
    execution = Execution(simulation, nb_ticks=8)
    execution.demarrer()
    durees, ticks_vus = [], set()
    while execution.est_active():
        debut = time.perf_counter()
        instantane = execution.instantane()
        durees.append(time.perf_counter() - debut)
        ticks_vus.add(instantane.tick)
        time.sleep(0.1)
    execution.attendre()
    cerveau.fermer()
    assert len(durees) >= 5
    assert max(durees) < 0.1
    assert execution.instantane().tick == 8
    assert len(ticks_vus) >= 2


def test_execution_remonte_une_erreur_du_fil(carte_grille):
    class ClientFautif:
        def generer(self, demande):
            raise KeyError("bogue")

    cerveau = CerveauLLM(ConfigurationCerveau(delai_ticks=1), ClientFautif())
    simulation = Simulation(
        Configuration(nb_agents=5), carte_grille, Journal(io.StringIO()), cerveau=cerveau
    )
    execution = Execution(simulation, nb_ticks=5)
    execution.demarrer()
    with pytest.raises(KeyError):
        execution.attendre()
    cerveau.fermer()


def test_execution_s_arrete_sur_demande(carte_grille):
    simulation = Simulation(Configuration(nb_agents=5), carte_grille, Journal(io.StringIO()))
    execution = Execution(simulation, nb_ticks=10_000_000)
    execution.demarrer()
    execution.arreter()
    execution.attendre(5)
    assert not execution.est_active()


def test_memoire_bornee():
    memoire = Memoire(3)
    for rang in range(10):
        memoire.retenir(str(rang))
    memoire.compter("travail")
    memoire.compter("travail")
    assert memoire.souvenirs == ["7", "8", "9"]
    assert memoire.faits == [("travail", 2)]


def test_prompt_identique_a_etat_egal_et_taille_bornee():
    configuration, cerveau = Configuration(), ConfigurationCerveau(taille_memoire=5)

    def prompt(nombre):
        memoire = Memoire(cerveau.taille_memoire)
        for rang in range(nombre):
            memoire.retenir(f"souvenir {rang:04d}")
        return construire_prompt(perception(), LIEUX, memoire, configuration, cerveau)

    assert prompt(5) == prompt(5)
    assert len(prompt(5)) == len(prompt(5000))


def test_prompt_contient_le_contexte():
    texte = construire_prompt(
        perception(noeud=3, budget_centimes=1205),
        LIEUX,
        Memoire(3),
        Configuration(),
        ConfigurationCerveau(),
    )
    assert "habitant n°0" in texte
    assert "08h00" in texte
    assert "12,05 €" in texte
    assert "Tu es : travail" in texte
    assert "loisir_1" in texte
    assert "Ton travail commence à 08h00 et dure 8 heures." in texte


def test_formats_lisibles():
    assert heure_lisible(8 * 3600 + 5 * 60) == "08h05"
    assert euros(1205) == "12,05 €"
    assert euros(5) == "0,05 €"


def plan_json(**champs):
    etape = {"lieu": "loisir_1", "activite": "loisir", "duree_minutes": 30, **champs}
    return json.dumps({"etapes": [etape]})


def test_plan_valide_analyse():
    assert analyser_plan(plan_json(), LIEUX, ConfigurationCerveau()) == [
        EtapePlan("loisir_1", "loisir", 30)
    ]


@pytest.mark.parametrize(
    "texte",
    [
        "pas du json",
        "[]",
        "{}",
        '{"etapes":"non"}',
        '{"etapes":[]}',
        '{"etapes":[12]}',
        plan_json(lieu="lune"),
        plan_json(lieu=["loisir_1"]),
        plan_json(activite="dormir"),
        plan_json(activite=["loisir"]),
        plan_json(duree_minutes=0),
        plan_json(duree_minutes=100000),
        plan_json(duree_minutes="30"),
        plan_json(duree_minutes=True),
        plan_json(duree_minutes=1.5),
        plan_json(activite="travail", lieu="loisir_1"),
    ],
)
def test_plan_invalide_refuse(texte):
    with pytest.raises(ReponseInvalide):
        analyser_plan(texte, LIEUX, ConfigurationCerveau())


def test_trop_d_etapes_refuse():
    etapes = [{"lieu": "domicile", "activite": "attente", "duree_minutes": 1}] * 7
    with pytest.raises(ReponseInvalide):
        analyser_plan(json.dumps({"etapes": etapes}), LIEUX, ConfigurationCerveau())


def test_schema_limite_les_lieux():
    schema = schema_plan(LIEUX, ConfigurationCerveau())
    travail, autres = schema["properties"]["etapes"]["items"]["anyOf"]
    assert travail["properties"]["lieu"]["enum"] == ["travail"]
    assert travail["properties"]["activite"]["enum"] == ["travail"]
    assert autres["properties"]["lieu"]["enum"] == ["domicile", "loisir_1", "travail"]
    assert "travail" not in autres["properties"]["activite"]["enum"]


def test_plan_va_au_lieu_puis_fait_l_activite():
    plan = PlanJour([EtapePlan("loisir_1", "loisir", 30)], LIEUX)
    assert plan.prochaine_intention(perception(noeud=1), 1000) == Aller(5, "loisir")
    assert plan.prochaine_intention(perception(noeud=5), 1000) == Activite("loisir", 1800)
    assert plan.prochaine_intention(perception(noeud=5), 1000) is None


def test_plan_saute_un_loisir_impayable():
    plan = PlanJour(
        [EtapePlan("loisir_1", "loisir", 30), EtapePlan("loisir_1", "attente", 5)], LIEUX
    )
    assert plan.prochaine_intention(
        perception(noeud=5, budget_centimes=10), 1000
    ) == Activite("attente", 300)


def test_le_budget_ne_devient_jamais_negatif_avec_des_loisirs_imposes(carte_grille):
    def loisirs(demande):
        etape = {"lieu": "loisir_1", "activite": "loisir", "duree_minutes": 1}
        return json.dumps({"etapes": [etape] * 6})

    configuration = Configuration(nb_agents=20, budget_initial_centimes=1500)
    _, simulation, _ = simuler(carte_grille, ClientFactice(loisirs), ticks=600, configuration=configuration)
    assert all(agent.budget_centimes >= 0 for agent in simulation.agents)


def test_banc_avec_client_factice():
    cerveau = ConfigurationCerveau()
    valide = json.dumps({"etapes": [{"lieu": "domicile", "activite": "attente", "duree_minutes": 5}]})
    client = ClientFactice(lambda demande: valide)
    for contexte in banc.CONTEXTES:
        assert banc.mesurer_sequentiel(client, cerveau, contexte, 4)["valides"] == 4
    stabilite = banc.mesurer_stabilite(client, cerveau, "soir", 3)
    assert stabilite["reponses_distinctes_meme_graine"] == 1
    assert stabilite["reponses_distinctes_entre_graines"] == 1
    assert banc.mesurer_debit(client, cerveau, 2, 4)["appels"] == 4


def executer_cli(*arguments, hash_seed="0"):
    return subprocess.run(
        [sys.executable, "-m", "ville.moteur", *map(str, arguments)],
        env={**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_ligne_de_commande_rejeu_identique(tmp_path):
    from ville.moteur.carte import Carte

    carte_json = tmp_path / "carte.json"
    carte_json.write_text(json.dumps(donnees_grille()), encoding="utf-8")
    carte = Carte.charger(carte_json)
    original, _, _ = simuler(carte, ClientFactice(plan_selon_graine), ticks=360)
    premier = tmp_path / "a.jsonl"
    premier.write_text(original, encoding="utf-8", newline="\n")
    second = tmp_path / "b.jsonl"
    resultat = executer_cli(
        "--carte", carte_json, "--heures", 1, "--rejeu", premier, "--journal", second, hash_seed="77"
    )
    assert resultat.returncode == 0, resultat.stderr
    assert second.read_bytes() == premier.read_bytes()
    assert "réflexions : 300" in resultat.stdout


def test_ligne_de_commande_refuse_un_rejeu_sur_une_autre_carte(tmp_path, carte_grille):
    original, _, _ = simuler(carte_grille, ClientFactice(plan_selon_graine), ticks=12)
    journal = tmp_path / "a.jsonl"
    journal.write_text(original, encoding="utf-8", newline="\n")
    autre = donnees_grille()
    autre["aretes"][0]["longueur"] = 99.0
    chemin_autre = tmp_path / "autre.json"
    chemin_autre.write_text(json.dumps(autre), encoding="utf-8")
    resultat = executer_cli(
        "--carte", chemin_autre, "--heures", 0.01, "--rejeu", journal, "--journal", tmp_path / "b.jsonl"
    )
    assert resultat.returncode == 3
    assert "rejeu impossible" in resultat.stderr


def test_ligne_de_commande_panne_ollama_replie_sans_planter(tmp_path):
    carte_json = tmp_path / "carte.json"
    carte_json.write_text(json.dumps(donnees_grille()), encoding="utf-8")
    journal = tmp_path / "a.jsonl"
    resultat = executer_cli(
        "--carte", carte_json, "--heures", 0.05, "--agents", 5, "--cerveau",
        "--url-ollama", "http://127.0.0.1:9", "--delai-max-appel", 1, "--journal", journal,
    )
    assert resultat.returncode == 0, resultat.stderr
    reflexions = evenements(journal.read_text(encoding="utf-8"), "reflexion")
    assert reflexions
    assert all(ligne["source"] == "regles" for ligne in reflexions)


@pytest.mark.ollama
def test_ollama_reel_repond_un_plan_valide():
    from ville.cerveau.client import ClientOllama

    cerveau = ConfigurationCerveau()
    for contexte in banc.CONTEXTES:
        texte = ClientOllama().generer(banc.demande_exemple(cerveau, contexte, 1))
        assert analyser_plan(texte, banc.LIEUX_EXEMPLE, cerveau)
