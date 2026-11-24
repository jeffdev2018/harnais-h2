---
name: qa-automation
description: Harnais QA & Ingénieur Tests avec Juge anti-flakiness (zéro sleep fixe, zéro nth-child, couverture nominale + cas d'erreur obligatoire en chmod 444).
---

# Harnais QA Automation — Tests Déterministes & Sans Flakiness

1. **Double couverture** : chaque fichier de test doit couvrir au moins un cas nominal ET un cas d'erreur/rejet (`400/403/404`, `raises`, `invalid`).
2. **Zéro attente fixe** : interdiction d'utiliser `time.sleep()`, `waitForTimeout()` ou `cy.wait()`.
3. **Sélecteurs résilients** : interdiction des `:nth-child()` et chaînes DOM fragiles ; utiliser `getByRole` ou `data-testid`.

## Cas limites appris (patcher 1 ligne conditionnelle par erreur réelle)
- `[Patch #1]` (UNIQUEMENT SI un test échoue en CI/local) : interdiction d'ajouter `@skip` ou `test.skip` pour faire passer la suite au vert.
