# Moteur stratégique

## Niveau réel du moteur

Le moteur de Poker IA est un conseiller **hybride et estimatif**. Il combine des tableaux préflop internes, une estimation d’équité Monte-Carlo, des indicateurs de situation et un modèle statistique des adversaires. Il ne constitue pas un solveur GTO exhaustif et ne calcule pas un équilibre exact de l’ensemble du No-Limit Hold’em.

La partie appelée « résolution locale » compare un ensemble discret d’actions et de sizings dans une abstraction limitée. Elle produit des EV contrefactuelles locales approximatives. Elle ne doit pas être décrite comme du CFR complet, du CFR+ convergé ou une preuve mathématique d’optimalité.

## Définition du conseil

Le meilleur coup affiché est :

> l’action légale ayant la meilleure espérance de gain estimée selon les cartes connues, les ranges adverses probables, l’historique des actions, les comportements observés, la profondeur des tapis, la position et le modèle stratégique utilisé.

Une décision de bonne qualité peut perdre la main. Inversement, une action mal classée peut gagner ponctuellement. Le résultat réel ne sert pas à renoter rétroactivement la qualité stratégique.

## Source, version et reproductibilité

- source préflop : seuils internes construits pour l’application, sans revendication de reproduction d’un solveur commercial ;
- version des tableaux : `preflop-fr-1.0` ;
- profondeurs de référence : 10, 15, 20, 25, 40, 60, 80, 100, 150 et 200 BB ou plus ;
- aléa : générateur pseudo-aléatoire contrôlé par une **seed** ;
- traçabilité : la version stratégique, la seed et le mode d’analyse sont associés au calcul lorsqu’ils sont disponibles.

À état, paramètres, version et seed identiques, l’échantillonnage est reproductible. Changer le nombre d’itérations, la version, la range ou la seed peut modifier une estimation proche du seuil.

## Cache stratégique borné

Les conseils sont mémorisés par une clé sémantique qui inclut l’état connu, les actions légales, les tapis, les profils adverses, le mode, le budget, la version et la seed. Le cache est limité à 256 entrées et évince les plus anciennes ; il ne peut donc pas croître indéfiniment pendant une longue session.

Lors de la mesure de livraison, un conseil rapide à froid a eu une médiane de 845,1905 ms en heads-up et de 2 542,1719 ms à six joueurs. Une répétition strictement identique servie par le cache a eu une médiane respective de 0,1429 ms et 0,2271 ms. Ces valeurs dépendent de la machine et ne transforment pas le calcul froid en solveur temps réel exhaustif.

## Pipeline de décision

### 1. Filtre des actions légales

Le moteur de règles fournit la liste autorisée ainsi que les bornes de mise. Le conseiller n’évalue jamais un check face à une mise, une relance non rouverte ou un montant hors bornes.

### 2. Référence préflop

Dans `preflop-fr-1.0`, la situation est d’abord ramenée à :

- position ;
- profondeur effective ;
- présence d’une relance et nombre agrégé de relances déjà observées ;
- score heuristique de la classe de main (paire, assortie/non assortie, hauteur et connectivité).

Le seuil d’ouverture est interpolé entre les profondeurs. Face à une relance, des seuils de continuation et de sur-relance sont ajoutés. Le nombre de joueurs, les positions exactes des relanceurs, les sizings et les antes ne sont pas des axes indépendants de cette version : ils ne sont pris en compte qu’indirectement, ou pas du tout. Il s’agit donc d’une abstraction heuristique versionnée, pas d’une matrice préflop exhaustive.

### 3. Équité pondérée

Les cartes inconnues sont tirées temporairement depuis les ranges adverses, en excluant les cartes mortes et connues. Pour chaque échantillon :

1. une combinaison adverse compatible est tirée ;
2. les cartes communes manquantes sont complétées ;
3. les meilleures mains sont comparées ;
4. les gains et partages alimentent l’estimation.

Le calcul prend en charge plusieurs adversaires et des ranges pondérées. Les cartes tirées n’ont aucune valeur de « vraies cartes », ne sont pas persistées et ne sortent pas du moteur.

L’estimation expose son nombre d’itérations et sa seed. Le champ de confiance du conseil est un score composite heuristique ; la version actuelle ne publie pas d’intervalle de confiance Monte-Carlo formel. Une faible marge entre deux actions doit être interprétée avec prudence.

### 4. Indicateurs

La version actuelle calcule et affiche directement :

- pot odds et équité minimale ;
- équité estimée ;
- SPR et tapis effectif ;
- fold equity estimée à partir d’une base heuristique et du profil adverse ;
- position dans la couche préflop.

Les cartes connues sont retirées du paquet, de sorte que leurs effets de bloqueurs/cartes mortes influencent implicitement l’échantillonnage. En revanche, la version actuelle ne publie pas de métriques séparées pour les outs propres, implied odds, reverse implied odds, avantage de range, avantage de nuts, initiative ou polarisation. La fold equity affichée est une approximation de modèle, pas une valeur observable exacte.

### 5. Comparaison d’EV locale

Le moteur compare les actions légales pertinentes. Les candidats de mise comprennent les fractions configurées par l’implémentation, la relance minimale et le tapis, tous bornés par les règles. Les montants disponibles sont visibles dans la liste des alternatives du conseil ; une fraction absente de cette liste n’a pas reçu d’EV distincte.

Une EV locale combine de façon simplifiée :

- coût immédiat ;
- probabilité estimée de folds ;
- équité lorsque l’action est suivie ;
- part du pot et taille future ;
- réactions adverses possibles ;
- pénalité d’incertitude ou de fragilité du modèle.

Elle ne développe pas l’arbre complet jusqu’à toutes les rivers pour tous les sizings. Deux valeurs proches ne doivent pas être lues comme une précision au jeton près.

### 6. Référence, exploitation et garde-fou

Trois sorties sont distinguées :

- **conseil équilibré** : classement de référence avec adaptation minimale ;
- **conseil exploitant** : ajustement basé sur les tendances observées ;
- **conseil final** : compromis pondéré par la confiance du modèle adverse.

Avec peu d’occasions, la stratégie finale reste proche de la référence. À confiance plus élevée, des adaptations mesurées deviennent possibles : value bet plus souvent contre un joueur qui suit trop, réduire les bluffs contre une calling station, voler davantage des blindes trop serrées ou défendre prudemment contre une agressivité avérée.

Le garde-fou ne garantit pas l’inexploitabilité ; il limite uniquement l’amplitude des écarts fondés sur des données faibles ou instables.

## Stratégies mixtes

Quand plusieurs actions ont une EV estimée suffisamment proche, elles peuvent former une stratégie mixte. Le conseil affiche alors les fréquences, l’action tirée pour cette occurrence et les alternatives acceptables. La seed rend le tirage reproductible.

Une action alternative appartenant à la fréquence acceptable n’est pas classée comme une erreur simplement parce qu’elle diffère de l’action tirée.

## Modes d’analyse

- **Rapide** : 700 essais Monte-Carlo par défaut, ensemble de sizings limité ; utilisé pendant le jeu.
- **Approfondie** : 4 000 essais par défaut ; destinée à une analyse demandée explicitement.
- **Experte** : 15 000 essais par défaut, principalement après la main.

Ces budgets peuvent être remplacés par un appel interne explicite. « Experte » décrit un budget d’échantillonnage supérieur, pas un arbre plus profond ni un solveur exact. L’annulation côté client interrompt l’attente HTTP ; selon le point atteint, le travail backend déjà lancé peut continuer jusqu’à la fin de son lot.

## Explications

L’explication est produite par des gabarits locaux à partir des résultats structurés déjà calculés : action, EV, équité, pot odds, SPR, range et confiance. Aucun modèle de langage ni second appel au moteur stratégique n’est nécessaire pour la rédiger.

Les libellés doivent indiquer :

- `exacte` uniquement pour une règle, un classement de showdown ou une entrée préflop retrouvée sans ambiguïté ;
- `estimée` pour l’équité, la fold equity et les EV ;
- `approximative` pour la résolution locale et les indicateurs dérivés ;
- le niveau de confiance pour toute adaptation exploitante.

## Limites d’interprétation

Le conseil dépend fortement des ranges et hypothèses de réponse. Une seed reproductible rend un calcul audit-able mais ne supprime pas l’erreur statistique. Une différence d’EV inférieure à l’incertitude doit être présentée comme une zone d’équivalence pratique. Voir [LIMITATIONS.md](LIMITATIONS.md) pour les limites détaillées.
