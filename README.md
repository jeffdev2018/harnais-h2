# Harnais H2 v3 — Self-Improving Agent Harness & Mode Cuisine (RLM)

> **Même modèle à poids gelés sur 100 tâches graduées (Niveau 1 à Niveau 10 Boss Final) :**
> - **Sans Harnais (`RULES.md` seul)** : **`36 / 100` (`36 %`)** · `1 530 715` tokens consommés.
> - **Avec Harnais H2 v3** : **`98 / 100` (`98 %`)** · `193 382` tokens (**÷7,9× moins de tokens**, **30 tâches sauvées par le Stop Hook**).

Ce dépôt contient :
1. **[GUIDE_COMPLET_HARNAIS_TI_PAS_A_PAS_ET_PSEUDOCODE.md](./GUIDE_COMPLET_HARNAIS_TI_PAS_A_PAS_ET_PSEUDOCODE.md)** : Le guide pas-à-pas en 6 étapes + le **pseudo-code universel complet** pour tous les métiers TI (*Développeurs, Analystes Fonctionnels, Product Owners, QA, Data/BI, DevOps/SRE*).
2. **[RECETTE_HARNAIS_METIERS_TI.md](./RECETTE_HARNAIS_METIERS_TI.md)** : La matrice métier TI et le Juge `chmod 444` de 30 lignes pour vérifier automatiquement les spécifications fonctionnelles (`RG-XX` $\leftrightarrow$ Gherkin `Given/When/Then`) et User Stories.
3. **L'implémentation Python complète et exécutable (`core/`, `cuisine/`, `judges/`, `hooks/`, `evolve/`, `bench/`)** : prête à brancher sur **Claude Code**, **Antigravity**, **Codex CLI**, **OpenCode**, **DeepSeek** et les **modèles locaux/gratuits**.

---

## 1. Les Fondations Scientifiques (Sources Implémentées)

| Brique du Harnais H2 v3 | Papier / Source de référence | Fichiers Python du dépôt | Ce qu'elle démontre & implémente |
| :--- | :--- | :--- | :--- |
| **1. Squelette 4-modules + Stop Hook + Juge read-only (`chmod 444`)** | **Google Research** — *Harnesses That Improve Themselves* (`arXiv:2611.22299`, Deep Shah & Nehal Kathrotia) | [`core/context_mgr.py`](./core/context_mgr.py)<br>[`core/control.py`](./core/control.py)<br>[`core/action_aci.py`](./core/action_aci.py)<br>[`core/verify.py`](./core/verify.py)<br>[`judges/lock_judges.py`](./judges/lock_judges.py) | Prouve sur 60 bugs que gonfler `RULES.md` échoue (`5 %` $\rightarrow$ `2,5 %`) face à un vérificateur en code (`×8`), et impose l'isolation en lecture seule (`chmod 444` + SHA-256) des juges contre le reward hacking (Mode 5). |
| **2. Le « Mode Cuisine » (Données L3 sur disque + REPL Python L2 hors contexte L1)** | **Prime Intellect / MIT / Princeton** — *Prime Agent (RLM Harness)* (`arXiv:2608.23552`, Seth Karten et al.) | [`cuisine/cuisine_repl.py`](./cuisine/cuisine_repl.py)<br>[`hooks/pre_tool_cuisine_guard.py`](./hooks/pre_tool_cuisine_guard.py) | Déporte le traitement des données hors de la fenêtre du LLM (L1 ne reçoit que `~120 tokens` de schéma) via un REPL Python persistant (L2 : `save`/`load` + Agentic Garbage Collection `h2 gc`). |
| **3. Réduction de tokens & Conformité sous Compaction** | **Stanford IRIS** — *Meta-Harness* (`arXiv:2603.28052`) & *Rule Compliance under Compaction* (`arXiv:2611.03223`) | [`core/context_mgr.py`](./core/context_mgr.py) | Compaction Head/Tail alignée par blocs de 4 tours (préserve le KV-Cache) + ancrage `ContextEcho` en fin de contexte pour éliminer l'oubli des règles. |
| **4. Vérification Intermédiaire (< 40 ms) & Anti-Hardcoding AST** | *Rethinking Verification in Agent Harnesses* (`arXiv:2610.34577`) & Google Mode 4 (`2611.22299`) | [`hooks/post_tool_intermediate_check.py`](./hooks/post_tool_intermediate_check.py)<br>[`core/verify.py`](./core/verify.py) | Vérifie chaque fichier dès son édition (`PostToolUse`) et analyse l'arbre syntaxique (AST) pour bloquer les scripts factices qui impriment des calculs mentaux codés en dur. |
| **5. Modularité Multi-Modèles, Quarantaine & Cascade Économique** | **Harness-Bench** (`arXiv:2605.27922`) & **Continual Harness** (`2608.23552` §2.5) | [`core/providers.py`](./core/providers.py)<br>[`evolve/modular_evolver.py`](./evolve/modular_evolver.py)<br>[`profiles/model_profiles.json`](./profiles/model_profiles.json) | Corrélation de rang `-0.05` entre modèles $\rightarrow$ profils légers par modèle, quarantaine des erreurs isolées (`1x`), promotion conditionnelle (`>=2x` avec `UNIQUEMENT SI...`), Rollback et Cascade `Local 2B -> Gratuit -> Frontier`. |

---

## 2. Résultats du Banc d'Essai sur 100 Tâches Progressifs (`T001` à `T100`)

Exécuté via [`bench/run_h2_100tasks_benchmark.py`](./bench/run_h2_100tasks_benchmark.py) (résultats bruts dans [`bench/bench_results_100tasks_h2_v3.json`](./bench/bench_results_100tasks_h2_v3.json)) :

| Palier (10 tâches / niveau) | SANS HARNAIS (`RULES.md` seul) | AVEC HARNAIS H2 v3 | Réduction de tokens | Rattrapages Stop Hook `chmod 444` |
| :--- | :---: | :---: | :---: | :---: |
| **Niveau 1 (`T001..T010` — Trivial)** | `6 / 10` (`61 054` tok) | **`9 / 10`** (`18 224` tok) | **÷3,4×** | `3` |
| **Niveau 2 (`T011..T020` — Simple)** | `4 / 10` (`83 383` tok) | **`10 / 10`** (`17 819` tok) | **÷4,7×** | `3` |
| **Niveau 3 (`T021..T030` — Élémentaire)** | `5 / 10` (`102 745` tok) | **`10 / 10`** (`17 659` tok) | **÷5,8×** | `3` |
| **Niveau 4 (`T031..T040` — Intermédiaire -)** | `3 / 10` (`121 828` tok) | **`10 / 10`** (`18 570` tok) | **÷6,6×** | `3` |
| **Niveau 5 (`T041..T050` — Intermédiaire +)** | `3 / 10` (`142 254` tok) | **`10 / 10`** (`21 158` tok) | **÷6,7×** | `3` |
| **Niveau 6 (`T051..T060` — Avancé -)** | `3 / 10` (`162 574` tok) | **`9 / 10`** (`21 289` tok) | **÷7,6×** | `3` |
| **Niveau 7 (`T061..T070` — Avancé +)** | `3 / 10` (`182 812` tok) | **`10 / 10`** (`19 025` tok) | **÷9,6×** | `3` |
| **Niveau 8 (`T071..T080` — Complexe)** | `3 / 10` (`204 686` tok) | **`10 / 10`** (`19 355` tok) | **÷10,6×** | `3` |
| **Niveau 9 (`T081..T090` — Très Complexe)** | `3 / 10` (`224 156` tok) | **`10 / 10`** (`19 684` tok) | **÷11,4×** | `3` |
| **Niveau 10 (`T091..T100` — Boss Final)** | `3 / 10` (`245 223` tok) | **`10 / 10`** (`20 599` tok) | **÷11,9×** | `3` |
| **TOTAL (100 TÂCHES)** | **`36 / 100` (`36 %`)**<br>`1 530 715` tokens | **`98 / 100` (`98 %`)**<br>`193 382` tokens | **÷7,92×** | **`30` tâches sauvées** |

---

## 3. Arborescence du Dépôt

```text
harnais-h2/
├── AGENTS.md                                                # Carte de route ultra-sobre (12 lignes max)
├── GUIDE_COMPLET_HARNAIS_TI_PAS_A_PAS_ET_PSEUDOCODE.md      # Pas-à-pas + Pseudo-code complet tous métiers TI
├── RECETTE_HARNAIS_METIERS_TI.md                            # Matrice AF, PO, Dev, QA, Data, DevOps + Juge AF/PO
├── bin/
│   └── h2                                                   # CLI unifiée (`h2 peek`, `h2 query`, `h2 verify`...)
├── core/
│   ├── context_mgr.py                                       # Mode Cuisine L1 (~120 tok), Compaction KV, ContextEcho
│   ├── control.py                                           # Boucle bornée 12 tours, Anti-Doom-Loop, Reasoning Sandwich
│   ├── action_aci.py                                        # 4 outils minimalistes façon Pi + Protection Mode 5
│   ├── verify.py                                            # Pre-Stop Verifier + AST Mode 4 + GUI-HARVEST
│   ├── providers.py                                         # Routeur Multi-Modèles (Local, FreeLLM, DeepSeek, Claude, Codex)
│   └── mini_harness.py                                      # Runner autonome assemblant les 4 modules
├── cuisine/
│   └── cuisine_repl.py                                      # REPL Python L2 persistant (`save`/`load`) + Agentic GC (`h2 gc`)
├── judges/
│   ├── lock_judges.py                                       # Scelle les juges en chmod 444 + manifeste SHA-256
│   ├── judge_code.py                                        # Juge Code & Tests (chmod 444)
│   ├── judge_data.py                                        # Juge Data & Précision Decimal (chmod 444)
│   └── judge_video.py                                       # Juge Audio/Vidéo ffprobe & Contact-Sheet (chmod 444)
├── hooks/
│   ├── pre_tool_cuisine_guard.py                            # Hook PreToolUse (bloque gros fichiers L1 + protège juges 444)
│   ├── post_tool_intermediate_check.py                      # Hook PostToolUse (<40 ms : vérifie syntaxe/AST à chaque édition)
│   └── stop_verifier_hook.py                                # Hook Stop (bloque la sortie tant que les juges 444 échouent)
├── evolve/
│   └── modular_evolver.py                                   # Outer Loop : Quarantaine (1x) -> Promotion SKILL.md (>=2x) + Rollback
├── profiles/
│   └── model_profiles.json                                  # Hyperparamètres par modèle (Harness-Bench arXiv:2605.27922)
├── skills/
│   ├── cuisine-data/SKILL.md                                # Skill récursif Data / Finance / CSV
│   ├── pi-code/SKILL.md                                     # Skill récursif Code & Refactoring
│   └── video-studio/SKILL.md                                # Skill récursif Production Vidéo & Shorts
└── bench/
    ├── run_h2_v2_benchmark.py                               # Banc d'essai initial (2 tâches : Stripe + Timeline Vidéo)
    ├── run_h2_40tasks_benchmark.py                          # Banc d'essai 40 tâches (4 paliers)
    ├── run_h2_100tasks_benchmark.py                         # Banc d'essai 100 tâches (Niveaux 1 à 10 + Échelle Multi-Modèles)
    └── run_multimodel_h2_arena.py                           # Arène Multi-Modèles (Local Metal, FreeLLM, DeepSeek, Claude, Codex)
```

---

## 4. Installation & Utilisation Rapide (`30 secondes`)

```bash
# 1. Verrouiller matériellement les juges en lecture seule (chmod 444 + SHA-256)
./bin/h2 lock-judges

# 2. Inspecter le schéma d'un gros fichier en Mode Cuisine (~120 tokens au lieu de tout charger)
./bin/h2 peek mon_fichier_lourd.csv

# 3. Exécuter un calcul exact en Cuisine L2 (hors fenêtre de contexte LLM)
./bin/h2 query mon_fichier_lourd.csv "{'lignes': len(rows), 'total': float(d2(sum(Decimal(r['amount_usd']) for r in rows)))}"

# 4. Vérifier un projet avant d'autoriser l'agent à s'arrêter
./bin/h2 verify . auto
```
