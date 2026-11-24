---
name: functional-analyst
description: Harnais Analyste Fonctionnel (AF / Business Analyst) avec Mode Cuisine sur cahiers des charges/transcriptions et Juge de traçabilité RG <-> Gherkin (chmod 444).
---

# Harnais Analyste Fonctionnel — Spécifications Sans Ambiguïté

1. **Sections obligatoires** : `## Acteurs`, `## Règles de Gestion`, `## Critères d'Acceptation (Gherkin)`, `## Cas d'Erreur`.
2. **Traçabilité 1:1** : chaque règle `RG-01`, `RG-02`... doit être citée dans au moins un scénario Gherkin (`Given/When/Then` ou `Soit/Quand/Alors`).
3. **Zéro mot flou** : interdiction d'écrire `TBD`, `à définir`, `etc.`, `à préciser`, `intuitif`, `rapide`.

## Cas limites appris (patcher 1 ligne conditionnelle par erreur réelle)
- `[Patch #1]` (UNIQUEMENT SI le flux modifie des données ou déclenche un paiement) : définir une règle `RG-XX` d'idempotence en cas de double-clic ou timeout réseau.
