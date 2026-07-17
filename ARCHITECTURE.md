# Architecture

## Vue d’ensemble

Poker IA suit une architecture locale en trois ensembles :

1. le frontend React/TypeScript affiche la table et conserve uniquement l’état d’interface nécessaire ;
2. l’API FastAPI valide les commandes et délègue les règles aux moteurs Python ;
3. SQLite conserve sessions, événements, conseils et profils, sans service distant.

```text
React + Zustand
      │ commandes et instantanés JSON
      ▼
FastAPI ── moteur Hold’em ── évaluateur / pots / stratégie
      │                              │
      └──── file de persistance ─────┴── SQLite
```

Le backend est l’autorité pour les actions légales, l’ordre de parole, les contributions, les pots et l’attribution du showdown. Le frontend ne reconstitue pas indépendamment ces règles.

## Arborescence fonctionnelle

```text
backend/
  app/
    engine/          cartes, évaluateur, pots, règles Hold’em, sessions
    strategy/        tables préflop, équité, conseil hybride
    opponents/       statistiques et modèle adverse
    persistence/     base SQLite et file d’écriture
    models.py        modèles d’échange et types communs
    api.py            routes HTTP locales
    main.py           application FastAPI et frontend statique
  alembic/            migrations
  tests/              tests Pytest
frontend/
  src/                composants React, store Zustand et appels API
  public/             icônes et logo
  tests/              tests Vitest/Playwright selon leur portée
desktop/
  launcher.py         serveur local + fenêtre WebView Windows
scripts/              installation, lancement et contrôle complet
data/                 données locales persistantes
```

## Modèle d’exécution

Une commande utilisateur suit ce trajet :

1. l’interface envoie une intention (`fold`, `check`, `call`, `bet`, `raise`, sélection de carte, validation du showdown) à la route de la session ;
2. l’API la valide par rapport à l’état courant détenu par le backend ;
3. le moteur produit un nouvel instantané déterministe de la main et un ou plusieurs événements ;
4. la réponse est immédiatement rendue ;
5. les événements persistants et les explications non indispensables sont traités hors du chemin critique.

La succession des joueurs et des rues ne dépend donc pas de la rédaction d’une explication ou de la vitesse de SQLite.

## État et journal d’événements

L’état de table comprend notamment les sièges, tapis, contributions, joueur actif, rue, cartes connues, action maximale, taille de la dernière relance complète et pots. Les mutations passent par les commandes du moteur. Les événements servent à :

- reconstruire l’historique action par action ;
- conserver ce qui était connu au moment d’une décision ;
- enregistrer le conseil et l’action effectivement choisie ;
- permettre la sauvegarde et la reprise sans confondre informations présentes et futures.

Une carte révélée au showdown est attachée à l’événement de révélation. Elle ne doit jamais être injectée rétroactivement dans un instantané antérieur.

## Frontend

Le frontend utilise React, TypeScript en mode strict, Vite et Zustand. Le store conserve l’instantané public reçu de l’API, les préférences d’affichage et la sélection locale en cours. Les composants principaux couvrent :

- configuration de table ;
- table et joueurs ;
- sélecteur permanent des 52 cartes ;
- barre d’actions ;
- conseil de Ryanchl ;
- saisie et résultat du showdown ;
- historique repliable et bilan de session.

Les actions restent disponibles pendant les traitements non essentiels. Le store vérifie encore que la session et le tour de Ryanchl sont courants lorsqu’il rafraîchit une explication. Il ne s’agit toutefois pas d’un protocole général de verrouillage optimiste par numéro de version ; voir [LIMITATIONS.md](LIMITATIONS.md).

## Backend et API

FastAPI expose uniquement l’interface nécessaire au client local. Les modèles d’entrée refusent les montants incohérents, cartes dupliquées, transitions de rue prématurées et actions non légales. Les erreurs fonctionnelles sont converties en messages français exploitables par l’interface.

Les modules sont séparés par responsabilité :

- `engine/holdem.py` : légalité et progression ;
- `engine/evaluator.py` : meilleure main de cinq cartes ;
- `engine/pokerkit_adapter.py` : frontière optionnelle de validation PokerKit, sans fuite de ses objets dans le domaine ;
- `engine/pots.py` : couches de contributions et éligibilité ;
- `engine/session.py` : rotation et cumul de session ;
- `strategy/` : estimation, jamais autorité des règles ;
- `opponents/` : observations et confiance ;
- `persistence/` : transaction SQLite et file d’écriture.

L’évaluateur interne reste l’autorité du classement livré. L’adaptateur PokerKit effectue une validation secondaire de compatibilité lorsqu’il est disponible ; son résultat n’est pas utilisé pour remplacer silencieusement le classement interne.

## Persistance

SQLite est choisi pour son déploiement local et transactionnel. Alembic versionne le schéma. La file de persistance sépare les écritures non critiques du traitement d’une action. À l’arrêt normal ou lors de « Sortir de la table », le système demande le vidage du buffer avant de confirmer la sauvegarde.

Le chemin est piloté par `POKER_IA_DATA_DIR`. Dans Docker, `./data` est monté dans `/app/data`. Dans l’application Windows empaquetée, le lanceur utilise par défaut le dossier applicatif de l’utilisateur.

## Frontières de sécurité

- le serveur natif écoute sur `127.0.0.1`, sauf le conteneur explicitement publié par Docker ;
- aucune API de casino ou d’argent réel n’est intégrée ;
- aucune capture, OCR, extension ou automatisation de clic n’existe ;
- les cartes adverses ne font pas partie de l’état public avant leur révélation ;
- les échantillons Monte-Carlo ne sont ni journalisés ni renvoyés au frontend ;
- un modèle de langage n’intervient dans aucune décision.

Le mode Docker publie le port `8765` uniquement sur `127.0.0.1`. Le serveur natif choisit automatiquement un autre port local si `8765` est déjà occupé.

## Reproductibilité

Les règles et l’évaluateur sont déterministes. Les calculs stochastiques acceptent une seed et indiquent la source/version de stratégie. La table préflop interne est identifiée par `preflop-fr-1.0`. Une seed identique, un même état et une même version doivent produire le même échantillonnage ; des versions ou paramètres différents peuvent changer le conseil estimé.

## Déploiements pris en charge

- Windows : application WebView construite par PyInstaller, ou lancement depuis les sources ;
- Bash : serveur Uvicorn servant le build frontend ;
- Docker Compose : build multi-étapes Node/Python et volume local pour les données.

Les commandes détaillées figurent dans [README.md](README.md).
