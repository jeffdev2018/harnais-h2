# Références Scientifiques & Bibliographie — Harnais H2 v3

Ce document répertorie l'ensemble des **papiers de recherche (arXiv)**, **études empiriques**, **dépôts open-source** et **guides d'ingénierie** sur lesquels repose chaque brique de code du **Harnais H2 v3**, avec leur **matrice de traçabilité vers les fichiers Python du dépôt** et leurs **entrées BibTeX**.

---

## 1. Les 5 Briques Fondatrices (Socle Harnais H2)

| # | Brique du Harnais H2 | Source Scientifique Exacte | Ce que l'étude démontre (Mesures Empiriques) | Implémentation dans ce dépôt |
| :- | :--- | :--- | :--- | :--- |
| **1** | **Le squelette mini-harnais (4 modules) + Stop Hook vérificateur + Juge read-only (`chmod 444`)** | **Google Research** — *Harnesses That Improve Themselves: A Unifying Framework for Self-Improving Agent Harnesses*<br>**Deep Shah & Nehal Kathrotia** (`arXiv:2611.22299`, Nov. 2026)<br>🔗 https://arxiv.org/abs/2611.22299 · [Texte intégral local](./references/2611.22299_harnesses_improve_themselves.txt) | • Part d'un mini-harnais Python de **142 lignes en 4 modules** (`context_mgr.py`, `control.py`, `action_aci.py`, `verify.py`).<br>• Prouve sur **60 bugs (SWE-bench Lite)** qu'ajouter des règles textuelles dans `RULES.md` fait **chuter** le score de **`5,0 %` à `2,5 %`** (les sorties non vérifiées doublent de 15 % à 30 %), tandis qu'une évolution modulaire avec **Stop Hook en code** monte à **`40,0 %` ($\times 8$)** tout en divisant les tokens par **2,5×**.<br>• Établit la taxonomie des **5 Modes de Défaillance** (Table II) et la **Défense Mode 5** (Table III.A.1) : verrouiller l'évaluateur en lecture seule (`chmod 444`) hors de portée d'écriture de l'agent. | • [`core/context_mgr.py`](./core/context_mgr.py)<br>• [`core/control.py`](./core/control.py)<br>• [`core/action_aci.py`](./core/action_aci.py)<br>• [`core/verify.py`](./core/verify.py)<br>• [`judges/lock_judges.py`](./judges/lock_judges.py)<br>• [`hooks/stop_verifier_hook.py`](./hooks/stop_verifier_hook.py) |
| **2** | **Le « Mode Cuisine » (Données sur disque L3 + REPL Python L2 hors contexte L1 + Mémoire persistante)** | **Prime Intellect / MIT / Princeton** — *Prime Agent: A Self-Improving RLM Harness*<br>**Seth Karten, Alex L. Zhang et al.** (`arXiv:2608.23552`, Août 2026)<br>🔗 https://arxiv.org/abs/2608.23552 · https://github.com/PrimeIntellect-ai/prime-agent · [Texte intégral local](./references/2608.23552_prime_agent.txt) | • Formalise la hiérarchie mémoire **L0 (Poids) $\cdot$ L1 (Contexte actif) $\cdot$ L2 (REPL Python & Sous-agents) $\cdot$ L3 (Disque : Fichiers, Historique, Skills)**.<br>• Déporte le traitement des données hors de la fenêtre du LLM via le paradigme **RLM (*Recursive Language Model*)** et l'**Agentic Garbage Collection** en L2.<br>• Fait passer un modèle à poids gelés de **`30,0 %` à `95,5 %`** sur **ARC-AGI-3**. *(L'analogie « Table L1 vs Cuisine L2 vs Garde-manger L3 » vulgarise cette architecture).* | • [`cuisine/cuisine_repl.py`](./cuisine/cuisine_repl.py)<br>• [`hooks/pre_tool_cuisine_guard.py`](./hooks/pre_tool_cuisine_guard.py)<br>• [`skills/cuisine-data/SKILL.md`](./skills/cuisine-data/SKILL.md) |
| **3** | **Réduire les tokens de contexte par le code du harnais** | **Stanford IRIS Lab** — *Meta-Harness: End-to-End Optimization of Model Harnesses*<br>**Yoonho Lee, Chelsea Finn et al.** (`arXiv:2603.28052`, Mars 2026)<br>🔗 https://arxiv.org/abs/2603.28052 | • Démontre qu'optimiser le **code exécutable du gestionnaire de contexte** du harnais bat les prompts statiques et les meilleurs compacteurs manuels de **`+7,7 points`** tout en consommant **4× moins de tokens de contexte**. | • [`core/context_mgr.py`](./core/context_mgr.py) (`build_data_schema_preview` ~120 tokens + `head_tail_compact`) |
| **4** | **Pourquoi un gros harnais figé ne se transfère pas d'un modèle à l'autre** | **Harness-Bench** — *Evaluating and Benchmarking Model-Harness Interactions Across Coding Agents* (`arXiv:2605.27922`, Mai 2026)<br>& **@joelniklaus** (SWE-bench Pro, Août 2026)<br>🔗 https://arxiv.org/abs/2605.27922 | • Mesure une **corrélation de rang de `-0,05`** entre les classements de harnais lourds sur différents modèles : le meilleur harnais monolithique pour un modèle A échoue souvent sur un modèle B.<br>• Sur SWE-bench Pro à poids fixes, changer uniquement le harnais fait passer **GLM-5.2 de `23 %` à `52 %` (`+29 pts`)** et **Gemma 4 26B de `15 %` à `36 %`**.<br>• D'où la nécessité d'un harnais **fin, modulaire (+ Stop Hooks)** couplé à des profils légers par modèle. | • [`profiles/model_profiles.json`](./profiles/model_profiles.json)<br>• [`core/control.py`](./core/control.py) (`load_model_profile`)<br>• [`core/providers.py`](./core/providers.py) |
| **5** | **Vue d'ensemble & Harnais Minimalistes (Pi 4-outils, Simon Willison, Anthropic, Karpathy)** | **RyanAlberts** — *best-of-Agent-Harnesses* (`187` harnais catalogués) & *Why the harness matters more than the model*<br>🔗 https://github.com/RyanAlberts/best-of-Agent-Harnesses · [Copie locale](./references/why-the-harness-matters.md) | • Synthétise le **YC Paper Club** (7 sept. 2026), la thèse d'**Andrej Karpathy** (*« The model is the kernel process, the harness is the OS »*), la définition de **Simon Willison** et les guides d'**Anthropic** (*Building Effective Agents* / *Effective Harnesses for Long-Running Agents*) + **Pi** (4 outils expressifs `view_file`, `edit_file`, `bash`, `finish` au lieu d'une liste de 50 plugins qui créent de la confusion — Mode 2). | • [`core/action_aci.py`](./core/action_aci.py)<br>• [`core/mini_harness.py`](./core/mini_harness.py)<br>• [`AGENTS.md`](./AGENTS.md) ($\le 12$ lignes) |

---

## 2. Les 6 Références Complémentaires (Ajouts Haute Performance Harnais H2 v2 & v3)

| # | Mécanisme Ajouté (v2 / v3) | Papier arXiv / Source Scientifique | Problème Résolu & Preuve | Fichier Python dans ce dépôt |
| :- | :--- | :--- | :--- | :--- |
| **6** | **Vérification Intermédiaire `< 40 ms` à chaque édition (`PostToolUse`)** | **Zhang et al.** — *Rethinking Verification in Agent Harnesses* (`arXiv:2610.34577`, Oct. 2026)<br>& **Vestrum** (cité dans `arXiv:2611.22299` Table I.D [37])<br>🔗 https://arxiv.org/abs/2610.34577 | Attendre uniquement le `Stop Hook` final laisse une erreur de syntaxe ou de logique commise au tour 2 se propager jusqu'au tour 12 (*error compounding*). Vérifier chaque fichier immédiatement après `Write`/`Edit` bloque l'erreur au tour même. | [`hooks/post_tool_intermediate_check.py`](./hooks/post_tool_intermediate_check.py)<br>[`core/verify.py`](./core/verify.py) (`verify_single_file_fast`) |
| **7** | **Ancrage `ContextEcho` + Compaction par blocs préservant le KV-Cache** | **Zha et al.** — *Do Agents Still Follow the Rules? Benchmarking Rule Compliance under Agent Context Compaction* (`arXiv:2611.03223`, Nov. 2026)<br>& **ContextEcho** (`arXiv:2606.17016`, Juin 2026)<br>🔗 https://arxiv.org/abs/2611.03223 · https://arxiv.org/abs/2606.17016 | Lorsqu'un harnais compacte l'historique d'une longue session, le résumé fait disparaître les contraintes initiales (*Instruction Fade-Out*). L'injection d'une ancre courte (`ContextEcho`) en fin de contexte après compaction restaure la conformité aux règles tout en gardant un préfixe stable par blocs de 4 tours pour le cache KV. | [`core/context_mgr.py`](./core/context_mgr.py) (`CONTEXT_ECHO_ANCHOR`, `CACHE_CHUNK_ALIGNMENT = 4`) |
| **8** | **Détecteur AST Anti-Hardcoding (Défense Mode 4) & Invariants Métier sans Vérité Terrain** | **Google Research** (`arXiv:2611.22299` §VI Mode 4 [78])<br>& **Xu et al.** — *Harness²: Recursive Agent Harnessing for an Open World* (`arXiv:2610.18813`, Oct. 2026)<br>🔗 https://arxiv.org/abs/2610.18813 | Un agent peut tricher en faisant un calcul mental approximatif puis en écrivant `print('{"total_usd": 123.45}')` sans jamais lire le CSV. L'analyse de l'arbre syntaxique (`ast.walk`) impose la présence réelle d'une lecture fichier (`IO=True`) et d'une boucle/agrégation (`Compute=True`). | [`core/verify.py`](./core/verify.py) (`check_ast_anti_hardcoding`)<br>[`cuisine/cuisine_repl.py`](./cuisine/cuisine_repl.py) |
| **9** | **Quarantaine Mémoire, Sanitizer Anti-Injection, Règles Conditionnelles (`UNIQUEMENT SI`) & Rollback** | **Karten et al.** — *Continual Harness* (`arXiv:2605.09998`, Mai 2026)<br>& **Google Research** (`arXiv:2611.22299` Table II Mode 1 & Table III.A.3)<br>🔗 https://arxiv.org/abs/2605.09998 | • **Mode 1 (*Rule Over-generalization*)** : une règle apprise sur 1 seul échec ou écrite sans condition de déclenchement dégrade les tâches simples.<br>• **Mode 5 (*Memory Poisoning*)** : une règle injectée en mémoire peut désactiver la sécurité (`verify=False`, `curl`).<br>• Solution : quarantaine à `1x`, promotion à `>=2x` sous condition explicite `(UNIQUEMENT SI ...)`, filtrage anti-injection, plafond de 450 tokens et snapshots versionnés (`h2 rollback`). | [`evolve/modular_evolver.py`](./evolve/modular_evolver.py)<br>[`skills/cuisine-data/SKILL.md`](./skills/cuisine-data/SKILL.md) |
| **10** | **Détection des Échecs Visuels Silencieux (Écran Noir Vidéo)** | **GUI-HARVEST** (cité dans `arXiv:2611.22299` Table I.D [38]) | Un rendu vidéo `.mp4` peut exister et avoir une durée valide (`ffprobe > 0.5s`), mais être un écran 100 % noir suite à un crash WebGL/HTML. L'analyse `ffmpeg blackdetect` sur les premières secondes bloque ces faux positifs. | [`core/verify.py`](./core/verify.py) (`check_video_not_black`)<br>[`judges/judge_video.py`](./judges/judge_video.py) |
| **11** | **Interface Agent-Ordinateur (ACI) & Taxonomie ETCLOVG** | **Yang et al. (Princeton)** — *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering* (`arXiv:2405.15793`, NeurIPS 2024)<br>& **Junjie Li et al.** — *Agent Harness Engineering: A Survey* (2026)<br>🔗 https://arxiv.org/abs/2405.15793 | • **SWE-agent** : lecture de fichiers fenêtrée (`120–160` lignes) et sorties shell bornées.<br>• **Survey ETCLOVG** : les 7 couches d'un harnais complet (*Execution, Tooling, Context, Lifecycle, Observability, Verification, Governance*) et la thèse de la contrainte liante (*la performance appartient à la paire `Modèle × Harnais`*). | [`core/action_aci.py`](./core/action_aci.py)<br>[`GUIDE_COMPLET_HARNAIS_TI_PAS_A_PAS_ET_PSEUDOCODE.md`](./GUIDE_COMPLET_HARNAIS_TI_PAS_A_PAS_ET_PSEUDOCODE.md) |

---

## 3. Liens Web & Vidéos d'Ingénierie de Référence

- **Y Combinator Paper Club (Sept. 2026)** — *Why the harness matters more than the model (with authors of Prime Agent, OpenJarvis & QM)* : https://www.youtube.com/watch?v=n9xKblqyQ28
- **Anthropic Engineering** — *Building Effective Agents* : https://www.anthropic.com/engineering/building-effective-agents
- **Anthropic Engineering** — *Effective Harnesses for Long-Running Agents* : https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- **OpenAI Engineering** — *Harness Engineering: Environment Design & Feedback Loops* : https://openai.com/index/harness-engineering/
- **Simon Willison** — *Defining LLM Agents & Harnesses* : https://simonwillison.net/2025/Sep/18/agents/
- **Andrej Karpathy** — *LLM OS (The model is the kernel process, the harness is the OS)* : https://x.com/karpathy/status/1707437820045062561 · https://github.com/karpathy/autoresearch

---

## 4. Citations BibTeX

```bibtex
@article{shah2026harnesses,
  title   = {Harnesses That Improve Themselves: A Unifying Framework for Self-Improving Agent Harnesses},
  author  = {Shah, Deep and Kathrotia, Nehal},
  journal = {arXiv preprint arXiv:2611.22299},
  year    = {2026}
}

@article{karten2026primeagent,
  title   = {Prime Agent: A Self-Improving RLM Harness},
  author  = {Karten, Seth and Zhang, Alex L. and Thomas, Kevin and M{\"u}ller, Sebastian and Bakouch, Elie and Auras, Daniel and Senghaas, Mika and Obeid, Fares and Dunas, Konstantin and Hagemann, Johannes and Jaghouar, Sami},
  journal = {arXiv preprint arXiv:2608.23552},
  year    = {2026}
}

@article{lee2026metaharness,
  title   = {Meta-Harness: End-to-End Optimization of Model Harnesses},
  author  = {Lee, Yoonho and Finn, Chelsea and others},
  journal = {arXiv preprint arXiv:2603.28052},
  year    = {2026}
}

@article{harnessbench2026,
  title   = {Harness-Bench: Evaluating Model-Harness Interactions Across Coding Agents},
  author  = {Harness-Bench Team},
  journal = {arXiv preprint arXiv:2605.27922},
  year    = {2026}
}

@article{zha2026rulecompliance,
  title   = {Do Agents Still Follow the Rules? Benchmarking Rule Compliance under Agent Context Compaction},
  author  = {Zha, et al.},
  journal = {arXiv preprint arXiv:2611.03223},
  year    = {2026}
}

@article{zhang2026rethinkingverification,
  title   = {Rethinking Verification in Agent Harnesses},
  author  = {Zhang, et al.},
  journal = {arXiv preprint arXiv:2610.34577},
  year    = {2026}
}

@article{xu2026harness2,
  title   = {Harness^2: Recursive Agent Harnessing for an Open World},
  author  = {Xu, et al.},
  journal = {arXiv preprint arXiv:2610.18813},
  year    = {2026}
}

@article{karten2026continualharness,
  title   = {Continual Harness: Self-Modifying Prompts, Skills, Memory, and Sub-Agents},
  author  = {Karten, Seth and others},
  journal = {arXiv preprint arXiv:2605.09998},
  year    = {2026}
}

@inproceedings{yang2024sweagent,
  title     = {SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  author    = {Yang, John and Jimenez, Carlos E. and Wettig, Alexander and Lieret, Kilian and Yao, Shunyu and Narasimhan, Karthik and Press, Ofir},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS)},
  journal   = {arXiv preprint arXiv:2405.15793},
  year      = {2024}
}
```
