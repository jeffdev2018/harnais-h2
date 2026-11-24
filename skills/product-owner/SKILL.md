---
name: product-owner
description: Harnais Product Owner (PO / PM) avec Mode Cuisine sur backlogs Jira/Linear CSV/JSON et Juge INVEST + DAG de dépendances + 3 cas limites (chmod 444).
---

# Harnais Product Owner — User Stories & Backlog Testables

1. **Structure INVEST** : `En tant que <rôle précis ≠ utilisateur>`, `Je veux <action>`, `Afin de <valeur mesurable>`.
2. **Les 3 cas limites obligatoires** : toujours spécifier l'État vide (`Empty state`), le Cas d'erreur API/Réseau, et les Permissions/Rôles.
3. **Chiffrage & Dépendances en Python L2** : calculer les scores R.I.C.E. et vérifier l'absence de cycle `blocked_by` via `judge_po.py`.

## Cas limites appris (patcher 1 ligne conditionnelle par erreur réelle)
- `[Patch #1]` (UNIQUEMENT SI découpage d'un Epic en User Stories) : interdiction de livrer une story purement technique sans critère Gherkin observable par un rôle métier.
