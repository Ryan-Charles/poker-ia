# Règles du No-Limit Texas Hold’em

Ce document décrit le modèle de règles appliqué par Poker IA. Le moteur de règles est indépendant du moteur de conseil : une estimation stratégique ne peut jamais rendre légale une action interdite.

## Participants, sièges et positions

Une table contient de 2 à 8 joueurs. `hero` est l’identifiant interne stable de Ryanchl ; son nom affiché est toujours **Ryanchl**. Un joueur absent ou éliminé n’est pas distribué et n’entre pas dans l’ordre de parole.

Le bouton avance au prochain joueur éligible à chaque nouvelle main. À trois joueurs ou plus :

- la petite blinde est le premier joueur éligible après le bouton ;
- la grosse blinde est le joueur suivant ;
- le premier joueur préflop est le joueur suivant la grosse blinde ;
- postflop, le premier joueur capable d’agir après le bouton parle en premier.

En heads-up, le bouton paie la petite blinde et agit en premier préflop. La grosse blinde agit en premier postflop.

## Blindes et antes

Le moteur accepte une petite blinde, une grosse blinde et, facultativement :

- une ante classique payée par chaque joueur distribué ;
- une big blind ante payée par le siège de grosse blinde.

Une obligation supérieure au tapis place le joueur à tapis pour ce qu’il possède, sans créer de jetons. Les blindes et antes participent aux contributions de la main et donc aux pots, mais les antes ne constituent pas une mise à suivre dans la rue préflop.

## Actions légales

Selon l’état courant, un joueur peut recevoir :

- **Se coucher** (`fold`) lorsqu’il est encore dans la main ;
- **Parole** (`check`) si son apport de rue est déjà égal au maximum ;
- **Suivre** (`call`) jusqu’au maximum courant, éventuellement à tapis ;
- **Miser** (`bet`) si aucune mise volontaire n’existe sur la rue ;
- **Relancer** (`raise`) vers un montant total lorsque la mise est ouverte ;
- **Tapis** comme mise, relance ou suivi limité par le tapis restant.

Le montant d’une relance est interprété comme **le total atteint sur la rue** (« raise to »), et non comme le seul supplément.

```text
montant_a_suivre = mise_maximale - contribution_de_rue_du_joueur
augmentation = total_vise - mise_maximale
```

Une action visant plus que le tapis est refusée ou plafonnée uniquement dans le cas explicite d’un suivi à tapis. Un joueur couché ou déjà à tapis ne reçoit plus la parole.

## Mise minimale et relance minimale

Une première mise complète doit normalement atteindre au moins une grosse blinde. Une relance complète doit augmenter le maximum d’au moins la taille de la dernière relance complète.

Exemple : ouverture à 6 après une grosse blinde de 2. L’augmentation complète est 4 ; la prochaine relance complète doit donc atteindre au moins 10.

Un joueur dont le tapis est insuffisant peut faire une relance incomplète à tapis. Elle augmente le montant à suivre, mais ne devient pas automatiquement une nouvelle relance complète.

## Réouverture des enchères

Le moteur mémorise qui a agi depuis la dernière relance complète.

- une relance complète rouvre l’enchère pour les joueurs encore capables d’agir ;
- une unique augmentation incomplète à tapis ne rouvre pas le droit de relancer à un joueur qui avait déjà répondu à la dernière relance complète ;
- un joueur qui n’avait pas encore agi conserve ses choix légaux ;
- plusieurs augmentations incomplètes sont appréciées par rapport au niveau de relance complet requis par l’état de la rue.

Cette distinction ne change pas le montant à suivre : les joueurs concernés doivent toujours égaler la contribution maximale, se coucher ou aller à tapis.

## Fin d’une rue

Une rue se termine uniquement lorsque tous les joueurs encore capables d’agir :

- ont répondu depuis la dernière relance complète ; et
- ont une contribution de rue égale au maximum, se sont couchés ou sont à tapis.

Si tout le monde fait parole, la rue se termine. Après le préflop, le moteur attend exactement trois cartes de flop ; après le flop, une turn ; après la turn, une river. Le passage de rue remet les contributions de rue à zéro, mais conserve les contributions totales.

Si tous les joueurs restants sont à tapis, aucune nouvelle décision n’est demandée. Les cartes communes manquantes sont demandées successivement jusqu’à la river.

## Fin anticipée

Lorsqu’un seul joueur reste non couché :

1. toute partie non suivie de la dernière mise est remboursée si nécessaire ;
2. le ou les pots lui sont attribués ;
3. aucune carte adverse n’est demandée ou inventée ;
4. la main est marquée « gagnée sans showdown » pour ce joueur.

Le résultat net reste le montant reçu moins la contribution totale à la main, et non le tapis final entier.

## Pots principal et secondaires

Les pots sont construits par couches de contributions totales. Les jetons d’un joueur couché restent dans la couche financée, mais ce joueur n’est jamais éligible à la gagner. Un joueur ne peut recevoir qu’une part d’un pot dont sa contribution atteint le seuil et pour lequel il n’est pas couché.

Une contribution dépassant seule toutes les contributions opposées est une mise non suivie et doit être remboursée, pas un pot dont le même joueur serait l’unique bénéficiaire. Le détail de l’attribution est dans [SHOWDOWN_ENGINE.md](SHOWDOWN_ENGINE.md).

## Showdown et égalités

Après la river, si au moins deux joueurs éligibles restent :

- les cartes de Ryanchl sont déjà connues ;
- l’utilisateur peut saisir les cartes réellement montrées par chaque adversaire ;
- un joueur peut être marqué comme n’ayant pas montré ;
- si les informations suffisent, l’évaluateur détermine automatiquement chaque pot ;
- sinon, l’interface exige une attribution manuelle explicite pour les pots indécidables.

Les égalités partagent le pot. Les jetons indivisibles sont distribués dans un ordre de siège déterministe à partir du bouton, conformément à la politique exposée dans le résultat du pot.

## Annulation et reprise

L’annulation et le rétablissement s’appuient sur les états/événements de la main et ne doivent pas réécrire l’information historique : une carte apprise plus tard n’apparaît jamais dans un état antérieur. Une session sauvegardée conserve les tapis et statistiques ; la main suivante remet à zéro les données propres à la main et fait tourner le bouton.

## Invariants principaux

- aucune carte ne peut apparaître deux fois ;
- aucun tapis ni pot ne peut être négatif ;
- la somme des tapis, contributions et montants attribués est conservée, hors ajout/retrait explicite entre les mains ;
- un joueur couché ne gagne aucun pot ;
- un joueur à tapis ne reçoit plus d’action ;
- une rue ne progresse pas tant que les réponses requises ne sont pas terminées ;
- aucune carte commune supplémentaire n’est demandée après une fin anticipée.

