# Rapport de validation — Poker IA 1.0.0

## Environnement

- validation finale : 16 juillet 2026 ;
- système : Windows 11, build 26200 ;
- Python : 3.12 (venv du projet) ;
- application strictement locale, avec jetons fictifs uniquement.

## Contexte de cette passe

Cette passe (16 juillet 2026, après-midi) valide la refonte de l’expérience de table en 19 points : placement des sièges en ordre horaire sur une ellipse (hero seul en bas, aucune bulle coupée ni chevauchée, mode « crowded » à 7-8 joueurs, allègement sous 880 px de hauteur) ; marqueurs de mise sur le tapis (1 jeton pour mise/call, +1 par niveau de relance) ; halos argenté/doré et grisé des joueurs couchés ; cartes de Ryanchl affichées en permanence sur sa bulle et surlignées en doré dans la grille ; vocabulaire des actions en anglais partout (Fold/Check/Call/Raise, boutons regroupés) ; onglets de l’assistant stratégique avec descriptions et couleur du conseil alignée sur les boutons ; suppression de l’enchaînement automatique de fin de main (bouton « Main suivante → » seul) ; sélecteur de cartes flottant au centre de la table pendant les saisies ; « Sortir de la table » avec remise à zéro et retour à la configuration ; persistance de la configuration dans `localStorage`. Les correctifs de fin de passe recentrent verticalement le sélecteur pour rendre les 52 cartes accessibles, limitent le dock d’actions à la largeur exacte de la table, renforcent fortement le contraste et la taille des tapis, affichent la mise de Ryanchl sur le tapis et convertissent tous les montants monétaires internes (par exemple `5`) vers leur valeur exacte (`0,05 €`).

La passe précédente du même jour (matin) couvrait la correction de `table_state_view`/`player_overrides`, la mise en page sans défilement et les premières extensions Playwright.

## Commandes exécutées et résultats exacts

Backend, depuis `backend/` :

```powershell
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
..\.venv\Scripts\python.exe -m mypy app
```

Frontend, depuis `frontend/` :

```powershell
pnpm exec tsc -b
pnpm exec eslint .
pnpm exec prettier --check .
pnpm exec vitest run
pnpm build
pnpm exec playwright test
```

| Contrôle | Résultat exact |
| --- | --- |
| Pytest | 113 tests collectés, 113 réussis ; 1 avertissement de dépréciation Starlette/TestClient concernant `httpx` |
| Ruff | tous les contrôles réussis |
| Ruff format | 34 fichiers déjà formatés (2 fichiers reformatés en tout début de passe : `app/presentation.py`, `tests/test_api_contract.py`) |
| MyPy | aucun problème dans 22 fichiers source |
| TypeScript strict (`tsc -b`) | réussi, zéro erreur |
| ESLint | réussi, zéro avertissement |
| Prettier | tous les fichiers conformes (le fichier `e2e/poker-ia.spec.ts` a été reformaté une fois pendant la passe) |
| Vitest | 3 fichiers, 36 tests réussis, durée 4,86 s |
| Vite (build) | build réussi ; CSS 59,33 Ko, JavaScript 311,63 Ko |
| Playwright | 22 tests réussis en 1,3 min, un worker Chromium |

## Scénarios et tests Playwright (22)

Aux 21 tests déjà couverts s’ajoute un test monétaire complet : le tapis de Ryanchl reste fortement contrasté (17 px, graisse forte, vert clair), sa mise est visible au-dessus de sa bulle et une valeur moteur `5` en unité « euros fictifs » est affichée exactement `0,05 €` dans le marqueur, les détails du siège et le journal d’actions. Les contrôles de disposition à 8 joueurs garantissent toujours zéro chevauchement à 1600×900 et 1366×768.

| Test | Résultat | Durée |
| --- | --- | ---: |
| Scénario A — relance, victoire préflop, résultat net exact et main suivante | réussi | 7,3 s |
| Scénario B — check jusqu’à la river, saisie adverse et gagnant automatique | réussi | 3,2 s |
| Scénario C — pot principal, deux pots secondaires, gagnants distincts et net exact | réussi | 3,0 s |
| Scénario D — conseil immédiat, explication, historique repliable et poursuite | réussi | 3,8 s |
| Scénario E — explication réellement différée sans bloquer action ni joueur suivant | réussi | 4,4 s |
| Scénario F — plusieurs mains, choix de sortie, bilan, erreurs et réouverture | réussi | 4,1 s |
| Scénario G — apprentissage agressif, bluffs révélés, garde-fou puis adaptation | réussi | 9,4 s |
| Scénario H — aucune carte adverse dans API, état visible ou DOM avant showdown | réussi | 1,2 s |
| Adaptation tablette 820×1180 — table, sélecteur et actions sans chevauchement horizontal | réussi | 0,9 s |
| Bilan de main — aucune section de mains révélées si personne n’a montré ses cartes *(nouveau)* | réussi | 1,5 s |
| Mise en page — aucun défilement à 1600×900 et 1366×768 dans toutes les phases *(nouveau)* | réussi | 6,3 s |
| Recommencer la main — confirmation en deux temps et remise à zéro *(nouveau)* | réussi | 2,8 s |
| Recommencer la main — Annuler referme la confirmation sans rien changer *(nouveau)* | réussi | 2,0 s |
| Remplacement de joueur en cours de main — nouveau nom et profil vierge *(nouveau)* | réussi | 2,8 s |
| Configuration — la grosse blinde pilotée dérive petite blinde et bouton *(nouveau)* | réussi | 0,6 s |
| Bureau compact — toutes les cartes restent accessibles et le dock s’arrête à la table *(nouveau)* | réussi | 2,1 s |
| Montants fictifs — le tapis ressort et la mise de Ryanchl affiche exactement 0,05 € *(nouveau)* | réussi | 1,1 s |

Les scénarios A, B et C utilisent l’auto-validation du showdown après la dernière carte requise, sans clic sur « Valider le showdown ». Le bilan reste affiché jusqu’au clic explicite sur « Main suivante → ». Le test de remplacement de joueur a été répété deux fois de suite pour écarter un risque d’instabilité : 2 réussites sur 2.

À l’occasion de cette adaptation, deux assertions du scénario C se sont révélées obsolètes (notation française R/D/V au lieu de K/Q/J dans la grille de cartes, et vérification de texte sur l’identifiant interne `hero`/`player-2` au lieu du nom affiché) ; elles ont été corrigées pour refléter le comportement réel de l’interface plutôt qu’affaiblies.

## Mesures de performance

Les mesures ci-dessous proviennent de la passe de validation précédente du même jour (`scripts\Mesurer-Performances.py`, horodatage `2026-07-16T01:46:53-0400`, avant les changements de mise en page de cette passe) : elles n’ont pas été ré-exécutées ici. Les changements de cette livraison portent sur l’interface (mise en page, panneau de bilan) et deux corrections d’affichage ; ils ne touchent pas le moteur de règles, le solveur ou la persistance mesurés ci-dessous.

| Mesure | Échantillons | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Action du moteur de règles | 500 | 0,3012 ms | 0,6978 ms | 1,9418 ms |
| Saisie/progression de cartes avec journal croissant | 500 | 11,2038 ms | 20,7274 ms | 42,1811 ms |
| Conseil rapide heads-up, 700 essais, à froid | 10 | 845,1905 ms | 1 263,1371 ms | 1 263,1371 ms |
| Même conseil heads-up, cache | 100 | 0,1429 ms | 0,2742 ms | 0,3320 ms |
| Conseil rapide six joueurs, 700 essais, à froid | 10 | 2 542,1719 ms | 2 734,8206 ms | 2 734,8206 ms |
| Même conseil six joueurs, cache | 100 | 0,2271 ms | 0,4565 ms | 0,5511 ms |
| Mise en file de persistance | 5 000 | 0,0034 ms | 0,0044 ms | 0,0706 ms |

Résultats complémentaires (même passe antérieure, non re-mesurés) :

- 2 000 cycles action/annulation : working set `+156 Kio`, mémoire privée `+0 Kio`, pic observé `72 596 Kio`, 3 événements actifs à la fin ;
- projection de 5 000 décisions historiques : `13,34 ms` ; working set avec les lignes `+5 192 Kio`, mémoire privée `+5 816 Kio`, working set relevé après libération `137 076 Kio` ;
- 5 000 écritures : 5 000 mises en file sans attente ;
- cache stratégique : 11 entrées utilisées pendant chaque série, 100 réponses en cache, limite globale de 256 entrées ;
- fenêtres frontend : 200 décisions au premier rendu, 100 dans l’historique en cours de partie.

Mesures de bout en bout avec le contrôleur de navigateur, le réseau local, le backend et le DOM : 316 ms pour passer de la configuration à la table, 334 ms pour sélectionner une carte. Elles ne doivent pas être interprétées comme le seul temps de rendu React.

## Paquet Windows et lancement réel

`scripts\Installer-Poker-IA.ps1` a été relancé pour embarquer tous les changements de cette passe (mise en page sans défilement, recommencer la main, remplacer un joueur, grosse blinde pilote, corrections d’affichage). Le script a réinstallé les dépendances backend/frontend, appliqué les migrations Alembic, reconstruit le frontend (`pnpm build`), reconditionné l’exécutable avec PyInstaller, puis exécuté l’auto-test embarqué (`POKER_IA_SMOKE_TEST=1`, base de données isolée) : code de sortie global `0`. La nouvelle version est :

```text
desktop/releases/20260716-190426/Poker IA/Poker IA.exe
```

Le raccourci Windows `Poker IA.lnk` a été vérifié après l’installation : sa cible (`TargetPath`) pointe exactement sur cet exécutable. Les versions antérieures restent présentes dans `desktop/releases/` mais ne sont plus référencées par le raccourci.

La fenêtre native reconstruite a été rouverte depuis le raccourci. Le processus actif provient bien de la version `20260716-190426`, l’API embarquée répond sur `127.0.0.1:8766`, avec `status: ok`, persistance `saved` et zéro écriture en attente. Le contrôle natif à 1518×710 confirme un tapis Ryanchl à `3,95 € fictifs` en vert clair 17 px, un marqueur de mise vert `0,05 €` portant le libellé accessible « Mise de Ryanchl : 0,05 € », ainsi que la conservation stricte des données : 5 sessions avant la session temporaire de validation, 5 après sa suppression.

## Réserves de validation

- Docker n’a pas été relancé dans cette passe : `Dockerfile` et `docker-compose.yml` restent non exécutés.
- Le lanceur Bash est fourni mais n’a pas été exécuté sous Linux/macOS dans cette passe.
- L’avertissement Starlette/TestClient est une dépréciation d’une dépendance de test ; il ne provoque aucun échec et ne concerne pas l’exécutable livré.
- Les mesures de performance de la section précédente datent de la passe antérieure du même jour et n’ont pas été ré-exécutées ; rien dans cette livraison ne devrait les invalider (aucun changement du moteur de règles, du solveur ou de la persistance), mais ce n’est pas une mesure vérifiée dans cette passe.
