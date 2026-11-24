---
name: cuisine-data
description: Harnais Mode Cuisine (Prime Agent RLM arXiv:2608.23552) pour CSV, JSON, transcripts, veille et calculs financiers en $ ou €.
---

# Harnais Mode Cuisine — Données, CSV & Transcripts

1. **Table (L1) vs Cuisine (L2) vs Garde-manger (L3)** :
   - Ne charge **jamais** un fichier `.csv`, `.jsonl`, `words.json` ou `transcript.json` entier en contexte L1.
   - Inspecte uniquement le schéma (~120 tokens) : `python3 harnais-h2/cuisine/cuisine_repl.py peek <fichier>`.
2. **Zéro calcul mental** :
   - Exécute tout tri, agrégation ou calcul financier en Python L2 avec `decimal.Decimal` (`ROUND_HALF_UP`).
3. **Validation par Juge `chmod 444`** :
   - Lance `python3 harnais-h2/cuisine/cuisine_repl.py run <script.py> <out.json> <cles_requises>`.

## Cas limites appris (patcher 1 ligne par erreur réelle)
- `[Patch #1]` (UNIQUEMENT SI la tâche concerne Déduplication temporelle (UNIQUEMENT si la tâche demande de filtrer les doublons)) : ignorer tout `CHARGE` ou `PAID` doublon dans la fenêtre demandée (`< 24h` ou `< 900s`) pour le même client normalisé + montant.
- `[Patch #2]` (UNIQUEMENT SI la tâche concerne Emails Gmail (`@gmail.com` / `@googlemail.com`)) : toujours mettre en minuscules, retirer `+tag` et tous les `.` avant `@` avant toute déduplication.
- `[Patch #3]` (UNIQUEMENT SI la tâche concerne Devises étrangères) : arrondir les frais FX ligne par ligne avec `d2()`, jamais sur le total.
- `[Patch #4]` (UNIQUEMENT SI la tâche concerne Frais cumulés (Stripe + FX)) : arrondir séparément `base_fee = d2(amt * Decimal('0.029') + Decimal('0.30'))` et `fx_fee = d2(amt * Decimal('0.015'))` avant de les additionner (`fee = base_fee + fx_fee`).
