# Moteur de showdown

## Entrée au showdown

Le showdown commence après la river lorsqu’au moins deux joueurs non couchés sont encore éligibles à un pot. Les cartes de Ryanchl sont déjà connues. Les cartes adverses ne sont créées dans l’état qu’après leur saisie explicite comme cartes montrées.

Un pot est résolu automatiquement seulement si les informations nécessaires pour comparer tous ses joueurs éligibles sont présentes. Sinon il reste `incomplet` jusqu’à une attribution manuelle explicite ; le moteur ne complète jamais une main inconnue.

## Meilleure combinaison de cinq cartes

Pour un joueur dont les deux cartes et les cinq cartes communes sont connues, l’évaluateur examine les combinaisons de 5 cartes parmi les 7 disponibles, soit 21 candidats. Chaque candidat reçoit une clé de classement comparable. La clé maximale constitue la meilleure main.

Après sélection, un adaptateur isolé tente également de faire accepter les cinq cartes par PokerKit `StandardHighHand`. Cette vérification est secondaire : les objets PokerKit ne traversent pas le reste de l’application et le classement affiché provient de l’évaluateur interne testé.

Cette méthode autorise correctement :

- l’utilisation des deux cartes privées ;
- l’utilisation d’une seule carte privée ;
- le board jouant entièrement, sans carte privée utilisée.

Contrairement à l’Omaha, le Texas Hold’em n’impose pas d’utiliser exactement deux cartes privées.

## Classement des mains

De la plus forte à la plus faible :

1. quinte flush royale — présentation particulière de la meilleure quinte flush à l’As ;
2. quinte flush ;
3. carré ;
4. full ;
5. couleur ;
6. quinte ;
7. brelan ;
8. double paire ;
9. paire ;
10. carte haute.

La quinte `A-2-3-4-5` est valide et son sommet vaut 5. L’As n’est pas utilisé au milieu d’une quinte (`Q-K-A-2-3` n’en est pas une).

## Clés de départage et kickers

Les égalités de catégorie sont comparées lexicographiquement :

- **quinte flush / quinte** : hauteur de la quinte ;
- **carré** : rang du carré, puis kicker ;
- **full** : rang du brelan, puis rang de la paire ;
- **couleur / carte haute** : cinq rangs décroissants ;
- **brelan** : rang du brelan, puis deux kickers ;
- **double paire** : paire haute, paire basse, puis kicker ;
- **paire** : rang de la paire, puis trois kickers.

Les couleurs n’ont aucun ordre entre elles. Deux clés identiques constituent une égalité exacte, même si les cartes privées diffèrent.

Le résultat expose la catégorie française, les cinq cartes retenues et la clé de départage afin que l’attribution soit vérifiable.

## Construction des pots par couches

Les pots sont construits à partir des contributions totales :

1. trier les niveaux de contribution positifs distincts ;
2. pour chaque intervalle entre deux niveaux, multiplier sa largeur par le nombre de contributeurs ayant atteint le niveau supérieur ;
3. inclure dans le montant les jetons des joueurs couchés ;
4. rendre éligibles uniquement les joueurs non couchés ayant atteint cette couche.

Exemple avec des contributions de 40, 100 et 180 :

| Couche | Calcul | Montant brut | Joueurs ayant financé |
| --- | ---: | ---: | --- |
| principal | `40 × 3` | 120 | les trois joueurs |
| secondaire 1 | `(100 - 40) × 2` | 120 | les deux plus gros tapis |
| secondaire 2 | `(180 - 100) × 1` | 80 | le seul plus gros apport |

La dernière couche financée par un seul joueur est une mise non suivie : elle est remboursée et n’est pas attribuée comme un pot. Un joueur couché peut financer une couche, mais n’apparaît jamais dans les joueurs éligibles.

## Attribution

Chaque pot est comparé indépendamment :

1. réunir ses joueurs éligibles ;
2. vérifier que chaque main nécessaire est connue ;
3. trouver la meilleure clé ;
4. conserver tous les joueurs partageant cette clé ;
5. diviser le montant en parts entières ;
6. attribuer les reliquats selon l’ordre de siège déterministe après le bouton.

Un joueur ne reçoit jamais de jetons d’un pot auquel il n’est pas éligible. Des pots différents peuvent avoir des gagnants différents.

Le rapport fournit pour chaque pot : montant, seuil de contribution, joueurs éligibles, gagnants, part par gagnant et éventuels jetons indivisibles.

## Attribution manuelle en cas d’information incomplète

Si un joueur éligible ne montre pas et que sa main est indispensable à la comparaison, le moteur ne déduit pas le gagnant à partir du seul comportement. L’utilisateur doit sélectionner le ou les gagnants parmi les joueurs éligibles au pot concerné. Une attribution invalide — joueur couché ou non éligible — est refusée.

Le résultat conserve la mention `attribution manuelle / cartes inconnues`. Les statistiques ne traitent pas cette attribution comme une main révélée et n’en déduisent pas un bluff.

## Résultat net

Pour chaque joueur :

```text
resultat_net_main = montant_total_recu - contribution_totale_main
nouveau_tapis = tapis_apres_mises + montant_total_recu + remboursement
```

Pour Ryanchl, le résultat affiché est strictement sa variation liée à cette main. Le tapis final entier n’est jamais présenté comme un gain.

Le statut d’attribution distingue :

- **Main gagnée** : Ryanchl est seul gagnant d’au moins un pot automatiquement résolu ;
- **Main perdue** : Ryanchl ne gagne aucun pot automatiquement résolu ;
- **Pot partagé** : Ryanchl partage au moins un pot gagné ;
- **Résultat incomplet** : un pot indispensable n’est pas résolu.

Le statut et le résultat financier restent distincts : gagner un petit pot secondaire peut coexister avec un net négatif sur la main. Le bilan affiche donc aussi le total engagé, le total reçu, le net en jetons, le net rapporté à la grosse blinde de la main, le nouveau tapis et le cumul de session.

## Conservation des jetons

Après remboursements et attributions :

```text
somme_des_contributions = somme_des_pots_attribues + somme_des_remboursements
```

et, hors recave ou retrait explicite entre les mains, la somme des tapis de la table est conservée. Les tests de pots et de showdown vérifient cet invariant en plus du gagnant attendu.

## Résumé de fin de main

Le résumé expose les gagnants, la meilleure main de chaque joueur révélé, les pots, le résultat de Ryanchl, son nouveau tapis, le conseil principal, l’action réellement choisie et leur éventuel écart. Les cartes non montrées restent absentes. La fermeture du résumé permet de lancer la main suivante sans effacer l’historique de session.
