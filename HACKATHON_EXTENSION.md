# Extension OpenAI Build Week — Coach de session

## Problème traité

Poker IA savait déjà enregistrer les décisions, estimer leur qualité et afficher un bilan statistique. Le joueur devait toutefois parcourir manuellement l’historique pour comprendre quoi travailler ensuite. Le Coach de session transforme ces données en plan de progression immédiatement exploitable.

## Travail ajouté pendant le hackathon

- score de décision sur 100, fondé sur la qualité estimée des choix et non sur le résultat financier ;
- cumul des écarts d’EV en grosses blindes ;
- sélection des trois décisions les plus coûteuses avec accès direct au replay détaillé ;
- plan d’entraînement de une à trois priorités selon la rue la plus fragile, la discipline, la confiance statistique et les écarts d’EV ;
- mise en évidence des points forts mesurables ;
- export local du rapport du coach au format Markdown ;
- garde-fous visibles rappelant que les estimations ne garantissent aucun résultat futur ;
- tests API et navigateur couvrant le nouveau contrat et son affichage.

## Confidentialité et fonctionnement

Le Coach de session est déterministe et fonctionne entièrement en local. Il agrège les décisions déjà conservées dans SQLite. Aucune carte, note adverse, session ou donnée personnelle n’est envoyée vers un service distant.

## Utilisation de Codex et GPT-5.6

Codex a servi à auditer l’architecture existante, définir le contrat du Coach de session, implémenter le calcul backend, construire l’expérience React, ajouter les tests et documenter la différence entre la base préexistante et l’extension du hackathon.

Preuves de développement déjà publiées :

- base préexistante importée : [`8430a42`](https://github.com/Ryan-Charles/poker-ia/commit/8430a42d4ccccf1ff16ed614913914c5646ff065) ;
- extension Coach de session : [`69a8e12`](https://github.com/Ryan-Charles/poker-ia/commit/69a8e12) ;
- dépôt public : https://github.com/Ryan-Charles/poker-ia.

Avant la soumission, compléter encore cette section avec :

- l’identifiant `/feedback` de la session Codex principale ;
- une courte description du passage où GPT-5.6 a été utilisé ;
- une capture ou un extrait du bilan du coach ;
- le lien vers la vidéo de démonstration.

## Démonstration conseillée

1. Créer une table avec des jetons ou euros fictifs.
2. Jouer trois mains et s’écarter volontairement d’un conseil sur au moins une décision.
3. Sortir de la table et ouvrir le bilan précédent.
4. Montrer le score, l’écart d’EV, la décision prioritaire et le plan d’entraînement.
5. Ouvrir le replay d’une décision depuis le coach.
6. Exporter le rapport Markdown.

## Positionnement responsable

Poker IA est un simulateur d’entraînement hors ligne. Il ne se connecte à aucune plateforme de poker, n’observe aucune table extérieure, ne mise pas d’argent réel et ne promet aucun gain. Son objectif est d’améliorer la qualité du raisonnement probabiliste et la compréhension des limites d’un modèle estimatif.
