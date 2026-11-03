# Projet : Ville émergente

Simulation d'environ 100 agents pilotés par des LLM sur une carte réelle (réseau routier OpenStreetMap). Les agents ont un budget, une mémoire, des relations, et choisissent de travailler, d'échanger, de se déplacer ou de parler. On injecte des événements (pluie d'argent, route bloquée, rumeur, élection locale) et on mesure ce qui émerge. Le but est autant le plaisir de la démo qu'une vraie démarche expérimentale : métriques, plusieurs graines aléatoires, comparaison de modèles.

## Règles de travail

- Code en français (noms de variables, fonctions, classes, messages de log et d'erreur).
- Aucun commentaire dans le code.
- Toujours proposer un plan avant d'implémenter une phase, puis attendre ma validation.
- Une branche par phase (phase-1-moteur, phase-2-cerveau, etc.), commits petits et cohérents, messages en français à l'impératif.
- Lancer les tests avant de déclarer une étape terminée, et me montrer le résultat.
- Toute source d'aléa passe par une graine unique configurable : à graine égale, la simulation doit donner exactement le même résultat.
- Ne pas ajouter de dépendance sans me la justifier en une phrase.
- Je veux apprendre : quand je demande « explique », détaille le choix d'architecture et ses alternatives. Quand je demande « critique », relis mon code au lieu de le réécrire.

## Stack

- Python 3.11 ou plus récent, tests avec pytest.
- Carte et routes : OSMnx et networkx.
- LLM local : Ollama, modèle par défaut qwen2.5:3b, modèle configurable.
- API : FastAPI avec uvicorn.
- Interface : JavaScript et Leaflet, qui affiche seulement les états et interpole les déplacements.
- Journal des événements : fichiers JSONL, analyse avec DuckDB et pandas.

## Architecture visée

```
ville/
  moteur/      carte, agents, boucle de temps
  cerveau/     appels au modèle, mémoire, décisions
  societe/     économie, relations, rumeurs, élection
  donnees/     journal d'événements, métriques
  api/         serveur FastAPI
  interface/   carte interactive
  experiences/ scénarios et comparaisons
  tests/
```

## Phases et critères de fin

1. Moteur : carte réelle, boucle de temps, agents à règles fixes sans LLM. Fin : la simulation tourne et reste reproductible à graine égale, couverte par des tests.
2. Cerveau : décisions par LLM local avec mémoire et planification. Seul un sous-ensemble d'agents réfléchit à chaque tour (paramètre configurable), le rendu reste découplé de l'inférence. Fin : 100 agents tiennent une heure simulée sans bloquer l'affichage.
3. Société : économie (salaires, prix, commerces), relations, rumeurs, élection. Fin : chaque mécanisme a un scénario de test.
4. Données : journal complet des événements, métriques (indice de Gini, vitesse de diffusion d'une rumeur, stabilité des prix), expériences comparées sur plusieurs graines et plusieurs modèles. Fin : un rapport reproductible avec chiffres.
5. Démo : interface interactive, mode « dieu » pour injecter des événements, relecture d'une simulation, vidéo et README.

## Contraintes

- Les appels au modèle sont coûteux : ne jamais faire réfléchir tous les agents à chaque tour.
- Toute décision d'un agent doit être journalisée avec sa graine, son contexte et sa réponse brute.
- Les résultats décrivent le comportement des modèles, pas la société réelle : le formuler ainsi dans les rapports.

## Commandes (à mettre à jour au fil du projet)

- Tests : pytest -q
- Lancer le serveur : uvicorn ville.api.serveur:app --reload (à créer en phase 4 ou 5)

## Instructions de compactage

Conserver les décisions d'architecture, les résultats de tests, l'état de la phase en cours et les problèmes ouverts.
