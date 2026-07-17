# Limites connues

## Usage strictement fictif

Poker IA est un simulateur local avec des jetons fictifs. Il n’est pas conçu pour assister une partie de poker réelle ou en ligne. Il ne doit pas être relié à un casino, une room, un compte joueur ou un système d’argent réel.

Le projet ne comporte volontairement ni OCR, ni capture d’écran, ni lecture automatique de table, ni overlay, ni extension de navigateur, ni bot de clic, ni import automatique d’une main en direct. Il ne remplace pas non plus les obligations légales ou règles d’une juridiction.

## Pas de solveur GTO exhaustif

Le moteur stratégique n’est pas un solveur complet de No-Limit Hold’em. Il ne parcourt pas l’arbre intégral, ne prouve pas une convergence vers un équilibre de Nash et ne fournit pas une stratégie inexploitable.

La « résolution locale » est une comparaison d’EV sur une abstraction limitée d’actions, de sizings, de réponses et de runouts. Elle ne doit pas être présentée comme du CFR/CFR+/MCCFR complet. Les termes « équilibré », « exploitant » et « expert » désignent des modes internes, pas une certification GTO.

## Tables préflop

Les tableaux `preflop-fr-1.0` sont une référence interne versionnée, pas l’export exact d’un solveur commercial. Ils modélisent principalement des seuils de force par position/profondeur et compressent la ligne adverse en présence/nombre de relances. Le nombre exact de joueurs, les positions des relanceurs, les sizings et les antes ne constituent pas des axes complets. L’interpolation et les pots multiway introduisent donc une approximation importante.

Une recommandation préflop peut être exacte **par rapport à l’entrée de table retrouvée**, sans être mathématiquement optimale dans le jeu réel complet.

## Monte-Carlo et EV

L’équité et les EV postflop dépendent :

- du nombre d’itérations ;
- de la seed ;
- de la qualité des ranges ;
- de l’abstraction des réactions et sizings ;
- des hypothèses de fold equity et de jeu futur.

La reproductibilité par seed ne rend pas l’estimation exacte. Deux actions proches peuvent changer d’ordre avec un autre échantillon. Le champ `confidence` est un score composite heuristique, pas un intervalle statistique Monte-Carlo. Les implied odds, reverse implied odds, avantages de range/nuts, outs propres et polarisation ne sont pas calculés comme métriques séparées dans cette version ; la fold equity et l’EV future sont des approximations simplifiées.

Le logiciel ne connaît jamais l’avenir de la main. Une recommandation favorable peut perdre à court terme.

## Modèle adverse

Le modèle Beta-Bernoulli et la décroissance temporelle quantifient des fréquences observées, pas des intentions. La version actuelle suit un noyau de statistiques (VPIP, PFR, limp, 3-bet, 4-bet, quelques folds, agression, sizings moyens et showdowns), pas l’intégralité des compteurs détaillés du cahier des charges. Les statistiques deviennent fragiles avec peu d’occasions, des adversaires changeant de style, des saisies incomplètes ou des contextes rares.

Les seuils de confiance et le retour vers un prior neutre limitent la surexploitation mais ne l’éliminent pas. La range Monte-Carlo est une pondération simplifiée par VPIP/agression, pas une matrice persistante par position, sizing et texture. Les étiquettes de profil sont des hypothèses statistiques. Aucun état mental — tilt, peur, frustration — n’est déduit.

Une attribution manuelle de showdown sans cartes ne prouve ni bluff ni value bet.

## Cartes inconnues

Avant le showdown, aucune « vraie » carte adverse n’est distribuée en secret. Les ranges sont probabilistes. Les cartes Monte-Carlo sont temporaires et ne correspondent à aucun joueur réel.

Au showdown, si un joueur indispensable ne montre pas, le gagnant de son pot ne peut pas être évalué automatiquement. Une attribution manuelle explicite est alors nécessaire et le résultat reste marqué comme incomplet ou manuel. Le moteur n’invente jamais les cartes manquantes.

## Règles et politiques de table

Le moteur vise les règles usuelles du No-Limit Texas Hold’em, mais certaines rooms peuvent appliquer des politiques différentes pour :

- l’ordre d’attribution d’un jeton indivisible ;
- les procédures de joueurs absents ;
- les big blind antes lorsque le tapis est inférieur aux obligations ;
- certaines séquences rares de relances incomplètes cumulées ;
- les changements de sièges, recaves et règles de tournoi.

La politique appliquée par Poker IA doit rester déterministe et visible dans le détail du pot. Le simulateur n’est pas un arbitre officiel d’une room particulière.

PokerKit est encapsulé comme validation secondaire. Si la bibliothèque est absente ou si son API devient incompatible, l’adaptateur le signale mais la version actuelle ne fait pas échouer le classement interne pour cette seule raison. La suite de tests de l’évaluateur reste donc la vérification principale.

## Persistance locale

SQLite convient à une utilisation locale mono-application. Le projet n’est pas conçu pour des écritures concurrentes depuis plusieurs machines ou plusieurs instances sur la même base.

La file asynchrone protège la fluidité, mais une extinction forcée du processus ou du système avant vidage peut perdre les derniers événements encore en mémoire. Le bouton « Sortir de la table » et l’arrêt normal réduisent ce risque ; ils ne remplacent pas une sauvegarde externe du dossier `data/`.

Les exports peuvent contenir l’historique de jeu saisi. Ils ne sont pas chiffrés par défaut et doivent être protégés comme tout fichier personnel local.

## Performance

Les temps de réponse dépendent du processeur, du nombre d’adversaires, du budget Monte-Carlo, de la taille de l’historique et du stockage. Le mode rapide privilégie la réactivité au détriment de la précision statistique. Les analyses approfondies utilisent davantage de ressources et peuvent être annulées.

Aucune cible de performance n’est considérée comme validée sans mesure inscrite dans `TEST_REPORT.md` sur la machine testée.

L’API d’historique applique les filtres mais renvoie encore toutes les lignes correspondantes : elle n’expose pas de curseur de pagination serveur dans cette version. Les résumés figés évitent de rejouer le moteur pour chaque ligne et le frontend borne le rendu initial à 200 décisions, mais une base exceptionnellement volumineuse gagnerait à disposer d’une pagination complète côté API.

## Interface et plateforme

Le poste de travail est prioritaire. La page de table ne défile jamais, ni verticalement ni horizontalement, aux résolutions 1920×1080, 1600×900 et 1366×768 : la table, le pot, les cartes communes, les sièges, le sélecteur de cartes et la barre d'actions tiennent toujours à l'écran ; le panneau de conseil et l'historique défilent en interne, jamais la page. La page de configuration, avant le début d'une partie, peut encore défiler normalement. L'adaptation tablette (≤980 px de large) reprend un empilement vertical classique avec défilement de page. Des fenêtres plus petites que ces résolutions cibles ou des niveaux de zoom extrêmes peuvent malgré tout nécessiter du défilement. Le lanceur Windows WebView dépend du runtime WebView2 disponible sur la machine ; le lancement dans un navigateur local reste une solution de repli.

Le conteneur publie le port `8765` sur l’interface locale `127.0.0.1` seulement. Toute ouverture réseau ou reverse proxy sort du modèle de sécurité prévu.

La livraison Windows native et son auto-test embarqué ont été vérifiés sur la machine cible. Docker n’y était pas installé : le `Dockerfile`, Docker Compose et le lanceur Bash sont fournis mais n’ont pas été exécutés dans cette validation. La fenêtre native exige WebView2 ; le lanceur navigateur reste la solution de repli.

Sur un dossier synchronisé par OneDrive, l’installateur crée volontairement une version horodatée au lieu d’écraser un exécutable qui pourrait être verrouillé. Des versions antérieures peuvent donc s’accumuler dans `desktop/releases` après plusieurs réinstallations ; le raccourci cible toujours la dernière version ayant réussi son auto-test.

Les requêtes d’action ne portent pas encore de numéro de révision optimiste explicite. L’interface séquentielle réduit le risque d’une commande obsolète, mais plusieurs clients pilotant simultanément la même session ne constituent pas un usage pris en charge.

## Interprétation de l’historique

L’écart d’EV est une différence entre estimations du même modèle. Il sert à comparer les actions dans ce cadre, pas à mesurer une perte monétaire réelle ou une vérité stratégique absolue. Une action gagnante peut être classée mauvaise et une action perdante excellente.

Une analyse experte relancée après la main peut utiliser un budget ou une version différents et produire un classement différent. Elle doit rester séparée du conseil original, avec ses propres paramètres et limites.

La relecture historique est consultative. Elle permet d’avancer et de revenir dans les événements réellement enregistrés, mais ne constitue pas encore un bac à sable permettant de bifurquer depuis une ancienne décision et de jouer une ligne alternative.

## Dépendances et versions

Les résultats reproductibles supposent les mêmes versions de code, tables, dépendances et paramètres. Une migration, mise à jour de l’évaluateur ou changement du générateur pseudo-aléatoire peut modifier des résultats. Les seeds et versions doivent être conservées avec les analyses importantes.
