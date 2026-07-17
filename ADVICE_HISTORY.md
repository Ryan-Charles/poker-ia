# Historique des conseils

## But

L’historique enregistre la qualité d’une décision séparément du résultat de la main. Il permet de revoir ce que Poker IA savait **au moment où Ryanchl devait agir**, sans réinjecter les cartes ou événements appris plus tard.

## Données enregistrées

Une entrée de conseil est rattachée à une session, une main et une décision stables. Selon les données disponibles, elle contient :

- date et heure ; rue, position et profondeur ;
- cartes connues de Ryanchl et board à cet instant ;
- tapis effectif, pot, montant à suivre et séquence d’actions antérieure ;
- profils et résumés de ranges adverses utilisés ;
- source/version du modèle, mode, seed et budget d’échantillonnage ;
- actions légales et EV estimée de chaque candidate ;
- conseil équilibré, exploitant et final ;
- montant total recommandé, pourcentage du pot et fréquences mixtes ;
- équité, équité minimale, pot odds, SPR et confiance ;
- explication courte structurée ;
- action et montant réellement choisis ;
- écart d’EV estimé et notation de décision ;
- résultat net de la main lorsqu’il devient disponible.

Les champs indisponibles restent explicitement absents ou `non calculé`; ils ne sont pas remplacés par zéro lorsqu’un zéro aurait un autre sens.

## Création des explications

L’explication ne lance pas une seconde résolution. Elle transforme les données structurées du conseil au moyen de gabarits français locaux : facteurs dominants, alternative acceptable, raison d’écarter une autre action et réserve liée à la confiance.

Cette séparation apporte deux garanties :

- le conseil peut être affiché avant le texte ;
- une rédaction lente ou en erreur ne change ni l’action recommandée ni l’ordre de parole.

Aucun modèle de langage ne décide ou ne rédige obligatoirement l’action. Les formulations ne doivent pas convertir une estimation en certitude.

## Sauvegarde asynchrone

Le backend place les événements de conseil dans une file locale. Le chemin critique d’une action met à jour l’état en mémoire et produit la réponse API ; l’écriture SQLite est effectuée par le consommateur de la file dans une transaction séparée.

En cas d’erreur temporaire :

- l’événement reste en mémoire pour une nouvelle tentative ;
- l’interface reçoit un avertissement non bloquant ;
- le tour continue ;
- « Sortir de la table » demande un vidage contrôlé de la file avant de confirmer la sauvegarde.

Cette stratégie réduit les blocages, mais une coupure brutale du processus avant vidage peut perdre les derniers événements non écrits ; cette limite est indiquée dans [LIMITATIONS.md](LIMITATIONS.md).

## Panneau repliable pendant la main

Le panneau « Conseils » est replié par défaut et affiche son nombre d’entrées. Déplié, il présente une liste chronologique compacte : main, rue, cartes connues, position, conseil, montant, action choisie, résultat provisoire/final, explication et confiance.

Ouvrir le panneau lit les entrées déjà en mémoire ou en base : cela ne rappelle pas le moteur stratégique. Le panneau reste de taille bornée, ne recouvre pas la barre d’actions ni le sélecteur et se ferme en un clic. Sélectionner une entrée ouvre son détail sans mettre la table en pause.

La liste compacte s’appuie sur un `history_context` figé avec l’instantané du conseil. Elle ne restaure ni ne rejoue le moteur de poker pour chaque ligne. L’écran d’historique rend au plus 200 décisions au premier affichage et le panneau en cours de partie conserve les 100 plus récentes ; le détail complet reste accessible à la demande.

## Sortie de table et bilan

Le bouton permanent « Sortir de la table » ne supprime pas la session. Si une main est en cours, l’interface propose de sauvegarder et sortir, terminer la main ou annuler. Après sortie, le bilan présente :

- nombre de mains et résultat cumulé en jetons/BB ;
- tapis initial et final ;
- victoires, défaites, partages et gains sans showdown ;
- plus gros pots gagnés et perdus ;
- historique filtrable des conseils.

Les filtres portent notamment sur la rue, la notation, le résultat, la position, l’adversaire et la profondeur. Les tris disponibles dépendent des champs réellement calculés : date, écart d’EV, résultat, confiance ou importance de l’erreur.

## Analyse détaillée

Une entrée peut ouvrir l’instantané complet de décision : joueurs, contributions, cartes alors connues, actions, ranges résumées, statistiques, pot odds, équité, SPR, EV, trois niveaux de conseil, choix réel, résultat ultérieur et limites du calcul.

L’analyse approfondie ou experte est une nouvelle tâche explicitement demandée depuis cet écran. Elle est distinguée du conseil original par son mode, son budget et sa seed. Elle ne réécrit pas le conseil historique et peut être annulée.

## Relecture action par action

Chaque étape sépare deux ensembles :

- **informations disponibles** : utilisables pour le conseil à l’époque ;
- **informations révélées ensuite** : visibles uniquement dans le contexte ultérieur.

Ainsi, les cartes adverses saisies au showdown ne figurent jamais dans le DOM, l’état ou la représentation d’une décision préflop/flop/turn/river antérieure. Le résultat final peut être joint comme annotation rétrospective, mais pas comme entrée du calcul original.

Lorsqu’un détail est demandé, la relecture restaure l’instantané puis avance sur les événements conservés avec un curseur stable. À chaque étape, la projection publique retire les cartes adverses qui n’étaient pas encore révélées. Cette relecture est consultative : elle n’altère ni la session en cours ni le conseil original.

## Protection contre les ralentissements

- fenêtres de rendu bornées à 200 décisions sur l’écran complet et 100 pendant la main ;
- instantanés sérialisables et résumés plutôt que recalculs à l’ouverture ;
- index SQLite sur les clés de session/main/décision et filtres principaux ;
- explication fondée sur les résultats existants ;
- file d’écriture hors chemin critique ;
- identifiants de tâches pour ignorer une analyse devenue obsolète ;
- budgets et annulation pour les analyses lourdes.

Les mesures observées pour la livraison appartiennent à `TEST_REPORT.md`; ce document décrit le mécanisme, pas un résultat de benchmark.
