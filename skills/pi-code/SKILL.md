---
name: pi-code
description: Harnais Code Minimaliste (Google arXiv:2611.22299 + Pi 4-Tools) avec lecture fenêtrée, Stop Hook de compilation/tests et Juge read-only chmod 444.
---

# Harnais Pi-Code — Développement & Refactoring Sobre

1. **Lecture fenêtrée uniquement** : lis par tranches de 120 à 160 lignes max (`view_file`), jamais un fichier de >300 lignes d'un bloc.
2. **Juge intouchable (`chmod 444`)** : ne modifie jamais un test ou un juge pour forcer un feu vert (Mode 5 Reward Hacking).
3. **Porte de sortie obligatoire** : `python3 harnais-h2/core/verify.py . code` doit retourner `OK` avant d'annoncer que la tâche est terminée.

## Cas limites appris (patcher 1 ligne par erreur réelle)
- `[Patch #1]` Interdiction d'appeler `finish` sur un `git diff` vide ou avec un marqueur de conflit `<<<<<<<`.
- `[Patch #2]` Interdiction d'introduire `verify=False`, `CERT_NONE` ou `@unittest.skip` pour contourner un échec.
