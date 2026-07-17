# Poker IA — dossier OpenAI Build Week

## État actuel

- Hackathon : OpenAI Build Week
- Participant : Ryan CHARLES, en solo
- Projet Devpost : https://devpost.com/software/poker-ia
- Dépôt public : https://github.com/Ryan-Charles/poker-ia
- État : brouillon, non soumis
- Catégorie conseillée : Apps for Your Life
- Date limite : 21 juillet 2026 à 20 h en Martinique
- Visuel : logo officiel Poker IA ajouté
- Extension réalisée : Coach de session

## Présentation courte à relire

Poker IA est un simulateur d’entraînement au poker entièrement local. Son nouveau Coach de session transforme la qualité des décisions en score sur 100, repère les écarts d’EV les plus coûteux, ouvre directement leur replay détaillé et produit un plan d’entraînement personnalisé. Le score ne dépend pas du résultat financier d’une main : une bonne décision reste bonne même si elle perd.

Le projet ne se connecte à aucune plateforme de poker, ne place aucune mise et n’utilise que des montants fictifs. Les cartes, notes adverses et sessions restent sur l’appareil.

## Différence entre l’existant et le travail du hackathon

Avant le hackathon, Poker IA permettait déjà de jouer localement, d’obtenir des conseils et de consulter un historique statistique. Pendant OpenAI Build Week, le projet a reçu :

- le score de décision sur 100 ;
- le cumul des écarts d’EV en grosses blindes ;
- les trois décisions prioritaires avec accès au replay ;
- un plan d’entraînement de une à trois étapes ;
- les points forts mesurables ;
- l’export du rapport en Markdown ;
- les messages d’usage responsable ;
- les tests API et navigateur du parcours complet.

## Script vidéo conseillé — moins de 3 minutes

1. **0:00–0:20 — Problème.** Expliquer qu’un résultat gagnant ne signifie pas forcément qu’une décision était bonne.
2. **0:20–0:50 — Application.** Montrer une table locale avec des jetons fictifs et le conseil stratégique.
3. **0:50–1:25 — Session.** Jouer ou résumer plusieurs mains, dont une décision volontairement éloignée du conseil.
4. **1:25–2:15 — Coach.** Sortir de la table, montrer le score, l’écart d’EV, la décision prioritaire et le plan d’entraînement.
5. **2:15–2:35 — Replay et export.** Ouvrir une décision depuis le Coach puis exporter le rapport Markdown.
6. **2:35–2:55 — Construction.** Dire explicitement que Codex avec GPT-5.6 a servi à auditer l’architecture, construire le Coach, écrire les tests et documenter l’extension.
7. **2:55–3:00 — Conclusion.** Rappeler que Poker IA est local, éducatif et sans argent réel.

La vidéo doit être publique sur YouTube ou Vimeo, avec une voix off audible.

## Éléments encore obligatoires avant soumission

- relire et personnaliser la présentation Devpost ;
- vérifier que le dépôt public est bien relié au projet Devpost ;
- enregistrer puis publier la vidéo de démonstration ;
- récupérer l’identifiant de la session depuis `/feedback` ;
- compléter les réponses finales demandées par OpenAI Build Week ;
- choisir la catégorie ;
- vérifier une dernière fois le projet, puis seulement lancer la soumission.

## Validation technique

- 117 tests backend réussis ;
- 38 tests frontend réussis ;
- 26 scénarios Chromium réussis ;
- contrôle TypeScript, ESLint, Prettier, Ruff et build de production réussis.
