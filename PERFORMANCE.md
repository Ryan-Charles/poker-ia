# Performance et non-blocage

## Portée de ce document

Ce fichier décrit les objectifs, frontières de latence et moyens de mesure. Les chiffres effectivement mesurés, la machine, les commandes et les résultats exacts de la livraison sont consignés dans `TEST_REPORT.md`. Une cible ci-dessous n’est pas une mesure acquise.

## Mesures de la livraison du 16 juillet 2026

Mesures locales sous Windows 11, Python 3.12.13, processeur Intel64 Family 6 Model 186, 12 processeurs logiques :

| Mesure | Échantillons | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Commande d’action du moteur | 500 | 0,3012 ms | 0,6978 ms | 1,9418 ms |
| Cycle de cartes et progression du moteur, journal croissant | 500 | 11,2038 ms | 20,7274 ms | 42,1811 ms |
| Conseil rapide heads-up, 700 essais, à froid | 10 | 845,1905 ms | 1 263,1371 ms | 1 263,1371 ms |
| Même conseil servi par le cache | 100 | 0,1429 ms | 0,2742 ms | 0,3320 ms |
| Conseil rapide à six joueurs, 700 essais, à froid | 10 | 2 542,1719 ms | 2 734,8206 ms | 2 734,8206 ms |
| Même conseil servi par le cache | 100 | 0,2271 ms | 0,4565 ms | 0,5511 ms |
| Mise en file d’une sauvegarde | 5 000 | 0,0034 ms | 0,0044 ms | 0,0706 ms |

La projection de 5 000 décisions d’historique a pris 13,34 ms. Le test de 2 000 cycles action/annulation a ajouté 156 Kio au working set, 0 Kio à la mémoire privée et a laissé 3 événements actifs. Les 5 000 sauvegardes ont toutes été mises en file sans attente.

Deux mesures de bout en bout incluant le contrôleur de navigateur, le réseau local, le backend et le rendu DOM ont donné 316 ms pour passer de la configuration à la table et 334 ms pour sélectionner une carte. Elles ne représentent pas le seul temps de rendu React.

## Budgets fonctionnels

L’expérience vise :

- retour visuel d’un clic d’action ou d’une carte sans latence perceptible ;
- progression vers le joueur suivant indépendante de l’explication ;
- ouverture de l’historique à partir de données déjà disponibles ;
- conseil rapide servi depuis une table, un cache ou un budget d’analyse borné ;
- sauvegarde SQLite hors du chemin critique ;
- analyse approfondie ou experte annulable ;
- interface utilisable pendant tout traitement non essentiel.

Les seuils chiffrés ne sont validés que s’ils apparaissent avec leur protocole dans `TEST_REPORT.md`.

## Chemin critique d’une action

Le chemin minimal comprend :

1. validation de la commande ;
2. application déterministe des règles ;
3. calcul du prochain joueur ou de la prochaine étape ;
4. production de l’instantané public ;
5. rendu frontend.

Il ne doit pas attendre :

- l’écriture définitive de l’historique ;
- la rédaction d’une explication ;
- une analyse stratégique approfondie ;
- l’agrégation complète des statistiques ;
- un export ou un rapport.

Le classement d’un showdown normal est déterministe et borné (21 combinaisons de cinq cartes par joueur connu) ; il peut rester synchrone tant que les mesures confirment sa faible latence.

## Tâches hors chemin critique

### Conseil et équité

Le conseil est calculé avec un budget dépendant du mode. Pendant le jeu, le mode rapide limite itérations et sizings. Les demandes portent un identifiant d’état : un résultat arrivé après une nouvelle action est conservé pour l’historique si pertinent, mais n’écrase pas le panneau du nouvel état.

### Explication

L’explication consomme les valeurs déjà calculées. Elle peut apparaître après l’action principale. Aucun rappel du solveur n’est effectué uniquement pour produire du texte.

### Persistance

Les événements sont placés dans une file locale puis écrits par lots transactionnels. Un échec temporaire déclenche une nouvelle tentative et un avertissement discret, sans empêcher l’action suivante. La sortie normale attend un vidage borné de la file.

### Modèle adverse

Les compteurs élémentaires sont mis à jour incrémentalement. Les agrégations plus coûteuses et résumés de profil peuvent être différés. Une mise à jour en retard ne change pas rétroactivement un conseil déjà enregistré.

## Cache

Les clés de cache incluent tout ce qui influence le résultat :

- cartes connues et rue ;
- séquence d’actions et actions légales ;
- tapis, contributions et positions ;
- ranges et version du modèle adverse ;
- version de stratégie ;
- mode, paramètres, nombre d’itérations et seed lorsque nécessaire.

Une clé incomplète risquerait de réutiliser un conseil incorrect. Les entrées sont bornées par une politique d’éviction afin d’éviter une croissance mémoire illimitée.

## Historique volumineux

Pour plusieurs milliers de conseils :

- l’API applique les filtres et produit la liste depuis le contexte historique figé, sans restaurer un moteur par ligne ;
- SQLite indexe les identifiants et critères de recherche ;
- le frontend borne le premier rendu à 200 décisions et le panneau en cours de partie aux 100 plus récentes ;
- le détail et la relecture événement par événement sont reconstruits à la demande ;
- ouvrir/fermer le panneau ne déclenche aucun recalcul.

## Annulation et nettoyage

Une analyse approfondie possède un jeton d’annulation. Le moteur vérifie régulièrement ce jeton entre lots de simulations. À la fin ou à l’annulation :

- les tableaux temporaires et mains simulées deviennent inaccessibles ;
- les callbacks/abonnements frontend sont libérés ;
- le résultat n’est publié que si l’identifiant d’état correspond encore ;
- les erreurs sont converties en état fonctionnel, sans bloquer la table.

## Méthode de mesure

Les tests de performance doivent mesurer séparément :

1. latence des commandes de règles, médiane et percentile élevé ;
2. temps de sélection/rendu d’une carte dans le navigateur ;
3. délai du premier conseil rapide ;
4. durée d’ouverture d’un historique de plusieurs milliers d’entrées ;
5. débit et impact d’écriture SQLite ;
6. mémoire avant/après une séquence longue ;
7. délai d’annulation d’une analyse ;
8. vidage de la file à la sortie.

Chaque résultat doit préciser système, versions, taille des données, nombre de répétitions, commande et unité. Une exécution isolée n’est pas suffisante pour revendiquer un percentile.

## Scénarios de non-blocage

Les tests fonctionnels couvrent au minimum :

- cliquer sur les actions pendant une écriture d’historique ralentie ;
- passer au joueur suivant avant l’arrivée de l’explication ;
- manipuler le sélecteur pendant une analyse ;
- ouvrir l’historique sans appel stratégique supplémentaire ;
- continuer après une panne SQLite temporaire simulée ;
- recevoir ensuite l’explication correspondant à la bonne décision ;
- sortir de table avec sauvegarde et vidage de file.

## Dégradation contrôlée

Si le calcul dépasse son budget, le logiciel préfère retourner une estimation moins précise mais clairement étiquetée, ou indiquer que l’analyse n’est pas disponible. Il ne fige pas l’interface et ne remplace pas silencieusement le moteur par une valeur factice.
