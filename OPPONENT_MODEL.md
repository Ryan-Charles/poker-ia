# Modèle des adversaires

## Principe

Chaque adversaire possède un profil local persistant. Ce profil décrit des fréquences observées et des hypothèses de range ; il ne « lit » pas la psychologie et ne connaît jamais les cartes cachées.

Le profil initial (inconnu, serré, large-agressif, calling station, etc.) est un **a priori**. Les actions réellement saisies le font évoluer progressivement. Une étiquette telle que « agressif » est toujours une synthèse statistique accompagnée d’un nombre d’occasions et d’une confiance, jamais un diagnostic psychologique.

## Observations et occasions

Une fréquence utilise un numérateur et un dénominateur d’occasions valides. Par exemple, un joueur n’entre dans le dénominateur du 3-bet que s’il a effectivement eu l’occasion de 3-bet. Les mains où il était absent, à tapis ou privé de cette possibilité ne comptent pas.

La version actuelle agrège :

- préflop : VPIP, PFR, limp, 3-bet, 4-bet et fold face à une ouverture ;
- postflop : agression et fold face au continuation bet lorsque l’appel fournit cette occasion ;
- position : VPIP et PFR ;
- sizings : moyenne par rue en proportion du pot ;
- showdown : nombre de mains révélées, victoire connue et bluff explicitement qualifié.

Le schéma prévoit des statistiques extensibles, mais les taux détaillés de limp-fold/call/raise, cold call, défense de blindes, barrels, check-raise, donk/probe, overbet et distributions complètes de sizings ne sont pas encore des compteurs distincts. Toutes les statistiques ne deviennent pas informatives à la même vitesse. L’interface affiche la valeur estimée avec le nombre d’occasions plutôt qu’une fausse précision.

## Régularisation Beta-Bernoulli

Les fréquences binaires utilisent une estimation Beta-Bernoulli. Pour un a priori `Beta(α₀, β₀)`, `s` succès pondérés et `e` échecs pondérés :

```text
posterieur = Beta(α₀ + s, β₀ + e)
moyenne = (α₀ + s) / (α₀ + β₀ + s + e)
```

Cette régularisation ramène les petits échantillons vers le profil neutre ou l’a priori choisi. La confiance dérive de la masse d’observation et de la largeur de l’intervalle crédible ; elle n’est pas une probabilité que l’étiquette psychologique soit « vraie ».

Pour les grandeurs continues, telles que le sizing moyen, le système conserve des agrégats pondérés et évite d’en tirer une conclusion lorsque le nombre d’observations est insuffisant.

## Faibles échantillons et garde-fou

La politique d’adaptation suit ces ordres de grandeur :

- moins de 10 occasions : adaptation presque nulle ;
- 10 à 30 : adaptation légère ;
- 30 à 100 : adaptation modérée ;
- au-delà de 100 : adaptation plus importante uniquement si la tendance est stable.

Ces seuils ne transforment pas automatiquement une statistique en certitude. Une forte contradiction entre historique récent et global réduit la confiance ou signale un possible changement de style.

## Pondération temporelle

Une décroissance temporelle donne davantage de poids aux observations récentes sans supprimer l’historique. La version actuelle applique un facteur fixe de `0,94` à chaque nouvelle occasion ; il n’est pas encore configurable dans l’interface. Le profil conserve :

- une vue globale régularisée ;
- une vue récente pondérée ;
- la période et le nombre effectif d’occasions ;
- un indicateur de divergence ou d’instabilité.

Une série courte de folds ou relances ne suffit pas à conclure à un changement durable.

## Ranges probabilistes

La range utilisée par le calcul est une distribution de tirage sur des combinaisons compatibles, jamais une main unique supposée. Dans la version actuelle, elle est paramétrée par :

- le VPIP régularisé ;
- l’agression régularisée ;
- la présence d’une action agressive observée dans la main ;
- la force heuristique de chaque combinaison candidate ;
- les cartes connues, retirées du paquet.

Pour chaque adversaire et essai, l’échantillonneur construit un sous-ensemble aléatoire borné de combinaisons compatibles, les pondère puis tire une main. Il ne maintient pas encore une grille persistante de 1 326 combinaisons mise à jour après chaque sizing, position et texture. Les cartes simulées servent uniquement au calcul d’équité ; elles ne deviennent jamais une observation du profil.

## Showdowns et informations révélées

Seules des cartes explicitement saisies comme montrées peuvent enrichir le profil. Une révélation peut documenter une value bet, un bluff ou semi-bluff dans le contexte de la ligne, mais une seule main reçoit un poids limité.

Si les cartes sont inconnues ou si le joueur ne montre pas :

- aucun bluff n’est inventé ;
- aucune catégorie de main n’est enregistrée ;
- le résultat de l’action reste utilisable comme action observée, pas comme preuve de composition de range.

## Hypothèses comportementales

Une fiche peut synthétiser « prudent », « agressif », « passif », « suit trop » ou « se couche trop ». Chaque hypothèse doit préciser :

- les statistiques qui la soutiennent ;
- la période et les occasions ;
- la confiance ;
- les éléments contradictoires ;
- la mention « hypothèse statistique, pas certitude psychologique ».

Le logiciel n’affirme jamais un tilt, une peur, une frustration ou une intention mentale.

## Influence sur le conseil

Le modèle exploitant propose un écart à la référence. Le poids réel de cet écart est borné par la confiance, la stabilité temporelle et la robustesse de l’action. Le modèle adverse ne peut ni rendre légale une action interdite, ni transformer une équité simulée en certitude.

Les profils peuvent être réinitialisés ou désactivés pour revenir à la stratégie de référence. L’import/export doit valider la version de schéma et ne doit jamais importer de cartes adverses comme si elles avaient été connues avant leur révélation.
