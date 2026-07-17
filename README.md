# Poker IA

**Poker IA** est une application locale d’entraînement au No-Limit Texas Hold’em. Elle permet de manipuler une table de 2 à 8 joueurs avec des jetons fictifs, de jouer toutes les décisions manuellement, d’obtenir un conseil stratégique estimatif pour **Ryanchl** et d’analyser les mains enregistrées.

> Cette application est un simulateur d’entraînement utilisant exclusivement des jetons fictifs. Elle n’est pas conçue pour assister un joueur sur une plateforme de poker en direct.

Elle ne se connecte à aucun casino, compte joueur, site de poker ou système d’argent réel. Elle ne lit pas l’écran, ne fait pas d’OCR, ne fournit pas d’overlay et n’automatise aucune action sur une table extérieure.

## Ce que contient le projet

- une interface React/TypeScript en français, avec table, sélecteur de cartes, barre d’actions, conseil, showdown et historique ;
- une API FastAPI locale et un moteur Python pour les règles, les pots, l’évaluation des mains et la stratégie ;
- une base SQLite locale avec migrations Alembic ;
- un modèle adverse statistique régularisé, fondé uniquement sur les actions saisies et les cartes réellement révélées ;
- des lanceurs Windows et Bash, ainsi qu’un lancement Docker Compose ;
- des tests backend, frontend et fonctionnels.

Le « meilleur coup » affiché est l’action légale ayant la meilleure espérance de gain **estimée** selon les informations connues et le modèle utilisé. Il ne prédit ni les cartes inconnues ni le résultat futur. Le moteur n’est pas un solveur GTO exhaustif : voir [STRATEGY_ENGINE.md](STRATEGY_ENGINE.md) et [LIMITATIONS.md](LIMITATIONS.md).

## Nouveautés

- **Coach de session** : le bilan transforme désormais l’historique en score de décision, écart d’EV cumulé, décisions prioritaires cliquables et plan d’entraînement personnalisé. Le diagnostic reste indépendant des gains ou pertes de la main et peut être exporté en Markdown.
- **Recommencer la main** : un bouton dans l’en-tête de la table remet la main en cours à son état initial (juste après les blindes/antes), après une confirmation en deux temps ; aucune carte ni action volontaire ne subsiste.
- **Remplacer un joueur** : depuis le tiroir d’édition d’un siège (✎), un nouveau joueur peut prendre la place d’un joueur existant, y compris en cours de main ; il hérite des mises déjà engagées mais démarre avec un profil adverse entièrement vierge.
- **Grosse blinde pilote** : en configuration, choisir quel joueur est grosse blinde dérive automatiquement la petite blinde et le bouton correspondants.
- **Cartes de showdown sur la table** : les cartes révélées volontairement s’affichent directement sur les sièges concernés, en plus du sélecteur.
- **Validation fluide du showdown** : le showdown se valide seul 600 ms après la dernière carte utile saisie. Le bilan reste ensuite affiché jusqu’au clic explicite sur « Main suivante → ».
- **Interface de table sans défilement** : sur ordinateur (1920×1080, 1600×900, 1366×768), la page de table tient entièrement à l’écran, dans toutes les phases (jeu, saisie des cartes, showdown, bilan). Le bilan de main s’ouvre en fenêtre superposée à défilement interne ; seul le panneau de conseil défile en interne pendant le jeu.
- **Notation des cartes** : l’interface utilise la notation anglaise (A, K, Q, J, 10 + ♠♥♦♣) partout, y compris dans le sélecteur et les mains révélées.

## Extension OpenAI Build Week

Le Coach de session constitue l’extension principale réalisée pendant OpenAI Build Week avec Codex. Il exploite les décisions déjà figées par le moteur local, sans transmettre les cartes, profils adverses ou historiques à un service distant. La méthode, les changements attribuables à la période du hackathon et les éléments de preuve attendus sont décrits dans [HACKATHON_EXTENSION.md](HACKATHON_EXTENSION.md).

## Installation et lancement sous Windows

Prérequis pour une installation depuis les sources : Python 3.12, Node.js 22 et `pnpm`. Les runtimes fournis par Codex sont aussi détectés automatiquement lorsqu’ils sont présents.

Depuis PowerShell, à la racine du projet :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Installer-Poker-IA.ps1
```

Ce script crée `.venv`, installe les dépendances, applique les migrations, construit le frontend, fabrique l’application Windows et exécute un auto-test du backend embarqué avant de créer le raccourci **Poker IA** sur le Bureau. Chaque installation validée est placée dans `desktop/releases/<horodatage>/Poker IA/` ; le raccourci et le lanceur choisissent la version valide la plus récente.

Pour démarrer ensuite :

```powershell
& '.\Lancer Poker IA.bat'
```

ou :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Lancer-Poker-IA.ps1
```

Le lanceur utilise l’exécutable construit s’il existe ; sinon il démarre le serveur local et la fenêtre native. Il essaie `127.0.0.1:8765`, puis le premier port libre jusqu’à `8795` si ce port appartient déjà à une autre application. La variable `POKER_IA_PORT` permet d’imposer un port précis. La fenêtre attend la réponse de santé propre à Poker IA avant de s’ouvrir.

## Installation et lancement sous Bash

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt
(
  cd backend
  ../.venv/bin/python -m alembic upgrade head
)
corepack enable
(
  cd frontend
  pnpm install --frozen-lockfile=false
  pnpm build
)
./scripts/lancer-poker-ia.sh
```

Ouvrir ensuite <http://127.0.0.1:8765> si aucun navigateur ne s’ouvre automatiquement.

## Lancement avec Docker

```bash
docker compose up --build
```

Puis ouvrir <http://127.0.0.1:8765>. Le dossier local `data/` est monté dans le conteneur afin de conserver la base entre les redémarrages.

## Développement

Backend :

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765 --reload
```

Frontend, dans un second terminal :

```powershell
Set-Location .\frontend
pnpm dev
```

L’URL et le proxy de développement sont définis dans la configuration Vite du projet.

## Tests et contrôles

Sous Windows :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-Complet.ps1
```

Sous Bash :

```bash
./scripts/test-complet.sh
```

Ces scripts appliquent les migrations, exécutent Pytest, Ruff, MyPy, le typage TypeScript, ESLint, Prettier, Vitest, le build et Playwright. Les nombres exacts, mesures et réserves de cette livraison figurent dans [TEST_REPORT.md](TEST_REPORT.md).

## Données et confidentialité

Les données sont stockées localement dans le répertoire configuré par `POKER_IA_DATA_DIR` (par défaut `data/` depuis les scripts, et le dossier applicatif local pour l’exécutable Windows). Aucun service externe n’est requis.

Avant le showdown, les cartes adverses réelles n’existent dans aucun champ d’état persistant ou réponse API. Les tirages temporaires utilisés par Monte-Carlo sont locaux au calcul, puis abandonnés. Les cartes révélées ne sont enregistrées qu’après saisie explicite au showdown. Voir [CARD_SELECTOR.md](CARD_SELECTOR.md).

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — composants, flux et persistance ;
- [POKER_RULES.md](POKER_RULES.md) — règles et progression d’une main ;
- [STRATEGY_ENGINE.md](STRATEGY_ENGINE.md) — calcul du conseil et niveau réel du moteur ;
- [OPPONENT_MODEL.md](OPPONENT_MODEL.md) — statistiques, confiance et ranges ;
- [CARD_SELECTOR.md](CARD_SELECTOR.md) — saisie et protection des cartes ;
- [SHOWDOWN_ENGINE.md](SHOWDOWN_ENGINE.md) — classement, pots et résultat net ;
- [ADVICE_HISTORY.md](ADVICE_HISTORY.md) — conseils, explications et relecture ;
- [PERFORMANCE.md](PERFORMANCE.md) — architecture non bloquante et mesures ;
- [LIMITATIONS.md](LIMITATIONS.md) — limites fonctionnelles et stratégiques ;
- [TEST_REPORT.md](TEST_REPORT.md) — commandes, résultats exacts, mesures et vérifications de livraison.

## Licence

Poker IA est publié sous [licence MIT](LICENSE).
