---
name: devops-sre
description: Harnais DevOps / SRE / Sécurité avec Juge d'infrastructure (zéro tag :latest, zéro USER root, zéro secret en clair, zéro port DB exposé sur 0.0.0.0 en chmod 444).
---

# Harnais DevOps & SRE — Infrastructure Reproductible & Sécurisée

1. **Versions épinglées** : interdiction du tag `:latest` dans `Dockerfile` ou `docker-compose.yml`.
2. **Moindre privilège** : interdiction de `USER root` ou `privileged: true`.
3. **Zéro secret ou port sensible exposé** : aucun token en dur (`sk-`, `ghp_`, `AKIA`) et aucun port DB/SSH (`22`, `5432`, `6379`, `27017`) ouvert sur `0.0.0.0`.

## Cas limites appris (patcher 1 ligne conditionnelle par erreur réelle)
- `[Patch #1]` (UNIQUEMENT SI définition d'un service conteneurisé) : toujours définir une sonde `healthcheck` explicite avant d'annoncer le déploiement prêt.
