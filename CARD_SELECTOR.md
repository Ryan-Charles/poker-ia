# Sélecteur de cartes

## Organisation permanente

Le panneau « Sélecteur de cartes » affiche les 52 cartes dans un ordre fixe :

- quatre lignes : pique, cœur, carreau, trèfle ;
- treize colonnes : As, Roi, Dame, Valet, 10, 9, 8, 7, 6, 5, 4, 3, 2.

Il reste intégré à la mise en page de la table, sans fenêtre modale. Sur un écran large il se place à droite ; lorsque l’espace se resserre il passe sous la table. Les zones de joueurs, le pot, le conseil et la barre d’actions ne doivent pas être recouverts.

## Emplacements d’une main

La sélection normale expose, dans cet ordre :

1. Carte Ryanchl 1 ;
2. Carte Ryanchl 2 ;
3. Flop 1 ;
4. Flop 2 ;
5. Flop 3 ;
6. Turn ;
7. River.

Le moteur de progression active seulement les emplacements compatibles avec la rue. Le prochain emplacement attendu est visuellement mis en évidence.

Un clic sur une carte disponible la place dans l’emplacement actif. Cliquer sur un emplacement existant le rend modifiable de façon explicite : le remplacement n’est jamais silencieux. Les commandes permettent d’annuler la dernière saisie, d’effacer la rue concernée ou de recommencer la sélection.

## Validation

Le frontend désactive immédiatement une carte utilisée, mais le backend répète toutes les validations. Il refuse notamment :

- une carte dupliquée ;
- une carte de Ryanchl réutilisée au board ;
- une carte commune présente deux fois ;
- une carte connue réutilisée chez un adversaire au showdown ;
- un flop qui ne contient pas exactement trois cartes ;
- une turn ou river fournie hors séquence ;
- une modification incompatible avec une action ou un état déjà validé.

Le backend reste l’autorité car une requête HTTP peut contourner une désactivation visuelle.

## Raccourcis et accessibilité

Les raccourcis de cartes utilisent le rang puis la couleur :

- `A` puis `S` : As de pique (`spade`) ;
- `K` puis `H` : Roi de cœur (`heart`) ;
- `Q` puis `D` : Dame de carreau (`diamond`) ;
- `J` puis `C` : Valet de trèfle (`club`).

Les rangs numériques utilisent `T` pour 10, puis `9` à `2`. L’aide visible rappelle la notation. Les flèches déplacent le focus dans la grille et Entrée sélectionne la carte focalisée. Les cartes indisponibles gardent un libellé accessible expliquant pourquoi elles ne peuvent pas être choisies.

Les raccourcis globaux d’action ne s’exécutent pas lorsqu’un champ texte ou numérique possède le focus.

## Showdown

La saisie adverse n’est activée qu’après l’entrée explicite dans l’étape `showdown`. Les deux cartes de Ryanchl restent préremplies. Pour chaque adversaire encore éligible à un pot, l’utilisateur peut :

- saisir deux cartes réellement montrées ;
- corriger une carte avant validation ;
- laisser les cartes inconnues ;
- déclarer « ne montre pas » ;
- passer au joueur suivant.

Les cartes déjà connues sont indisponibles dans la même grille. Si une attribution automatique dépend de cartes absentes, l’application marque le résultat incomplet et demande une attribution manuelle du pot concerné ; elle n’invente jamais les cartes manquantes.

## Protection des cartes adverses

Avant le showdown, il n’existe aucun champ de « vraies cartes adverses » :

- pas dans le DOM, même masqué par CSS ;
- pas dans le store Zustand, les propriétés de composant ou le stockage navigateur ;
- pas dans l’instantané public ou les réponses API ;
- pas dans SQLite, les exports, les événements ou les logs ;
- pas dans une infobulle, un attribut d’accessibilité ou un message d’erreur.

Le backend ne pré-distribue pas secrètement de cartes adverses. Pour Monte-Carlo, il construit une combinaison temporaire à l’intérieur d’une itération à partir d’une range pondérée, l’utilise pour l’évaluation puis abandonne cette donnée. Les échantillons et la seed ne permettent pas à l’interface d’accéder à une « vraie » main, puisqu’aucune n’a été assignée.

Après le showdown, une carte n’est enregistrée que si l’utilisateur l’a explicitement révélée. Dans une relecture, elle apparaît à partir de son événement de révélation, jamais dans les états antérieurs.

## Représentation canonique

Les cartes utilisent un code canonique rang + couleur à l’interface de l’API (par exemple `As`, `Kh`, `Qd`, `Jc`, selon la casse normalisée par le backend). Toute entrée est normalisée puis vérifiée dans le paquet standard de 52 cartes. Les libellés français et symboles `♠ ♥ ♦ ♣` sont une présentation, pas une seconde source d’identité.
