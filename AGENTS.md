# AGENTS.md — Harnais H2 (12 lignes max · Zéro blabla · Google 2611.22299)

## Commandes & Vérification Déterministe
- Vérification avant arrêt : `python3 harnais-h2/core/verify.py . auto`
- Aperçu Mode Cuisine L1   : `python3 harnais-h2/cuisine/cuisine_repl.py peek <fichier>`
- Calcul Python isolé L2   : `python3 harnais-h2/cuisine/cuisine_repl.py run <script.py> <out.json>`

## Garde-fous d'exécution (Invariants)
- Mode Cuisine : ne jamais lire un CSV, `words.json`, `transcript.json` ou lockfile entier dans le chat.
- Tout calcul sur chiffres, dates ou tableaux passe par Python (`Decimal`, `ROUND_HALF_UP`).
- Les juges `harnais-h2/judges/judge_*.py` sont en lecture seule (`chmod 444`) : interdiction d'y toucher.
- Garder le contexte sous 70 % : charger `harnais-h2/skills/<domaine>/SKILL.md` uniquement à la demande.
