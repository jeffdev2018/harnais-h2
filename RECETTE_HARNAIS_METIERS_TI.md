# La Recette Universelle du Harnais H2 pour les Métiers TI
*(Développeurs, Analystes Fonctionnels, Product Owners, QA, Data/BI, DevOps/SRE)*

> **Preuve mesurée sur 100 tâches (Niveaux 1 à 10)** : Même modèle à poids gelés — **Sans Harnais : `36 %`** (`1,53M` tokens) $\rightarrow$ **Avec Harnais H2 : `98 %`** (`193k` tokens, **÷8× moins de tokens**).

---

## Partie 1 — Le Pas-à-Pas Universel en 5 Étapes (30 minutes pour n'importe quel métier TI)

Quel que soit ton métier dans l'IT, un harnais ne change **jamais** d'architecture. Il se construit toujours en **5 gestes dans cet ordre précis** :

### Étape 1 — Séparer la « Table » et la « Cuisine » (Garde d'Entrée `PreToolUse`)
- **Le problème** : Un Analyste Fonctionnel qui colle un cahier des charges de 120 pages, un PO qui colle 400 tickets Jira exportés en CSV, ou un Dev qui charge un fichier de logs de 50 Mo dans le chat noie l'attention du modèle (le score s'effondre et les tokens explosent $\times 10$).
- **Le geste** :
  - **Sur le disque (L3 — Le Garde-manger)** : tu poses tes gros fichiers bruts (`.csv` Jira, `.json` Swagger/OpenAPI, exports SQL, logs, transcriptions d'ateliers).
  - **Sur la table du LLM (L1 — Le Contexte)** : tu n'autorises **que l'étiquette (~120 tokens)** : les noms des colonnes + 2 lignes d'exemple (`h2 peek fichier.csv`), ou la table des matières du document.
  - **Dans la cuisine (L2 — Python hors contexte)** : l'agent interroge ou filtre le fichier via un petit script Python (`h2 query`) sans jamais faire entrer le fichier entier dans la conversation.

### Étape 2 — Écrire la Carte de Route en 12 lignes max (`AGENTS.md`)
- **La règle d'or (Google `arXiv:2611.22299`)** : Au-delà de 12 à 30 lignes, chaque règle textuelle supplémentaire dilue les précédentes (le score passe de 5 % à 2,5 %).
- **Le squelette à copier-coller (identique pour tous les métiers)** :
  ```markdown
  # AGENTS.md (12 lignes max)
  ## 1. Commandes obligatoires
  - Aperçu données L1 (~120 tok) : `h2 peek <fichier>`
  - Requête/Calcul Python L2     : `h2 query <fichier> "<expression>"`
  - Vérification avant arrêt     : `h2 verify . <code|data|spec>`

  ## 2. Invariants non négociables
  - Interdiction de lire un fichier > 30 Ko en entier dans le chat.
  - Zéro calcul ou comptage de tête : tout comptage/chiffrage passe par Python.
  - Interdiction absolue de modifier le fichier juge (`chmod 444`).
  - Charger `.agents/skills/<metier>/SKILL.md` uniquement quand la tâche correspond.
  ```

### Étape 3 — Coder le « Juge Intouchable » de ton métier et le sceller en `chmod 444`
- **Le principe** : Ne demande jamais à l'IA *« Relis-toi et vérifie que ton travail est complet »* (elle répondra toujours *« Oui, j'ai bien vérifié ! »*). Écris un script Python de **30 lignes** (`judge_<metier>.py`) qui vérifie **mécaniquement** que le livrable respecte la Definition of Done (DoD), puis verrouille-le en lecture seule :
  ```bash
  chmod 444 judge_<metier>.py
  ```
- **Pourquoi `chmod 444` ?** Parce que si l'agent n'arrive pas à passer le test, son réflexe naturel (Mode 5 *Reward Hacking*) est de modifier le test pour qu'il renvoie toujours `OK`. En `chmod 444`, l'OS lui renvoie `Permission denied` : il est obligé de corriger son livrable.

### Étape 4 — Brancher les 2 Portes Automatiques (`PostToolUse` + `Stop Hook`)
- **En cours de route (`PostToolUse`)** : Dès que l'agent écrit ou modifie un fichier (une spec JSON/Markdown, un diagramme Mermaid, du code, un CSV), un micro-check (< 40 ms) vérifie que la syntaxe est valide. S'il y a une faute, il la corrige **au tour même** sans empiler d'erreurs.
- **À la sortie (`Stop Hook`)** : Quand l'agent veut dire *« J'ai terminé »*, le Stop Hook lance ton `judge_<metier>.py` (`chmod 444`).
  - Si le juge renvoie une erreur (`exit 1`), le bouton *Stop* est **bloqué** et la liste exacte des manques est renvoyée à l'agent (qui se corrige tout seul en 1 ou 2 tours, comme sur nos **30 rattrapages réussis** du banc d'essai).

### Étape 5 — Faire grandir le `SKILL.md` d'UNE seule ligne par erreur réelle (avec condition)
- **Interdiction d'inventer 50 règles d'avance.**
- Tu commences avec un fichier `SKILL.md` quasi vide.
- Chaque fois que ton Juge `chmod 444` bloque l'agent deux fois sur le même piège, tu ajoutes **1 ligne** sous la forme :
  `- [Patch #N] (UNIQUEMENT SI <condition précise>) : <action exacte à faire ou interdire>.`
- *(Pourquoi « UNIQUEMENT SI » ? Parce que sans condition de déclenchement, un modèle Frontier comme Claude ou GPT appliquera la règle même sur les tâches simples où elle ne s'applique pas !)*

---

## Partie 2 — Adaptation Clé en Main par Métier TI

| Métier TI | 1. Ce qui reste en Cuisine L3 (`h2 peek` / `h2 query`) | 2. Ce que vérifie ton Juge `chmod 444` (`judge_<metier>.py`) avant d'autoriser `Stop` | 3. Exemple de `[Patch #1]` appris dans ton `SKILL.md` |
| :--- | :--- | :--- | :--- |
| **Analyste Fonctionnel (AF / BA)** | • Transcriptions brutes d'ateliers métiers (`.txt`/`.json`)<br>• Schémas de base de données / dictionnaires de données (`.sql`, `.csv`)<br>• Anciennes specs de 100 pages | **Juge de Spécification Fonctionnelle (`judge_af.py`)** :<br>1. Toutes les sections obligatoires sont présentes (*Acteurs, Préconditions, Flux nominal, Flux d'exception, Règles de gestion `RG-01..N`*).<br>2. Chaque règle de gestion `RG-XX` est liée à au moins 1 critère d'acceptation Gherkin (`Given / When / Then`).<br>3. Zéro mot flou interdit (*« etc. », « à définir », « TBD », « rapide », « intuitif »*).<br>4. Les diagrammes `mermaid` compilent sans erreur de syntaxe. | `- [Patch #1] (UNIQUEMENT sur un flux de paiement ou formulaire) : toujours spécifier le comportement exact en cas de double-clic / timeout réseau (idempotence).` |
| **Product Owner (PO / PM)** | • Export CSV/JSON du backlog Jira / Linear / NoteGen (500 tickets)<br>• Retours utilisateurs & verbatims support (`.csv`)<br>• Métriques d'usage Analytics | **Juge de User Story & Backlog (`judge_po.py`)** :<br>1. Format INVEST strict : *En tant que [persona précis ≠ "utilisateur"] / Je veux [action] / Afin de [valeur mesurable]*.<br>2. Présence obligatoire des cas limites (état vide, erreur API, permissions/rôles) en Gherkin.<br>3. Vérification en Python que les dépendances entre tickets (`blocked_by`) ne forment aucun cycle et que le chiffrage/priorité R.I.C.E. est calculé par script, pas de tête. | `- [Patch #1] (UNIQUEMENT lors du découpage d'un Epic) : interdiction de créer une User Story technique sans impact utilisateur visible ni critère Gherkin testable.` |
| **Développeur (Dev / Tech Lead)** | • Lockfiles (`package-lock.json`, `pnpm-lock.yaml`)<br>• Fichiers sources > 300 lignes (lus par tranches de 120 lignes)<br>• Logs d'exécution & dumps JSON | **Juge de Code & Tests (`judge_code.py`)** :<br>1. Compilation / typage (`py_compile`, `tsc --noEmit`, `node --check`).<br>2. Exécution des tests unitaires impactés (`.harness_test.sh`).<br>3. Détection anti-triche AST (Mode 4 & Mode 5) : bloque si l'agent a supprimé une assertion, ajouté `@skip`, `verify=False`, `any` sauvage, ou codé le résultat en dur. | `- [Patch #1] (UNIQUEMENT lors d'une modification de signature de fonction) : vérifier tous les appelants via recherche avant d'éditer.` |
| **QA / Ingénieur Tests** | • Matrices de couverture CSV<br>• Captures HAR réseau & traces Playwright/Cypress<br>• Jeux de données de test (`.json`, `.csv`) | **Juge de Couverture & Robustesse (`judge_qa.py`)** :<br>1. Chaque `RG-XX` de l'Analyste Fonctionnel possède au moins 1 test passant ET 1 test d'erreur (cas négatif).<br>2. Aucun `sleep()` arbitraire ou sélecteur fragile (`nth-child`) dans les tests E2E.<br>3. Le test échoue réellement quand on injecte une mutation (preuve que le test ne passe pas à vide). | `- [Patch #1] (UNIQUEMENT sur les tests E2E Playwright) : utiliser exclusivement getByRole / data-testid, jamais de sélecteur CSS de style.` |
| **Data / BI / FinOps** | • Exports CSV/Parquet de facturation cloud, Stripe, CRM (10k+ lignes)<br>• Tables SQL de staging | **Juge de Réconciliation (`judge_data.py`)** :<br>1. Interdiction AST du calcul mental (le script Python doit ouvrir la source et boucler).<br>2. Arrondi `Decimal('0.01', ROUND_HALF_UP)` ligne par ligne.<br>3. Zéro `null` / `NaN` et équilibre comptable vérifié (`Somme(lignes) == Total`). | `- [Patch #1] (UNIQUEMENT si déduplication d'emails) : normaliser les adresses Gmail (minuscules, retirer '.' et '+tag' avant '@').` |
| **DevOps / SRE / Sécurité** | • Logs serveurs / Kubernetes (`kubectl logs`)<br>• États Terraform (`terraform.tfstate`)<br>• Rapports de scan CVE (`.json`) | **Juge d'Infra & Sécurité (`judge_ops.py`)** :<br>1. Validation déterministe (`terraform validate`, `docker compose config`, `yamllint`).<br>2. Scan secrets : zéro clé/token en dur, zéro port sensible (`22`, `5432`, `6379`) ouvert en `0.0.0.0/0`.<br>3. Healthcheck réel (`HTTP 200`) avant de déclarer un déploiement terminé. | `- [Patch #1] (UNIQUEMENT sur un Dockerfile ou Compose) : interdiction d'utiliser le tag ':latest' ou d'exécuter le conteneur en 'root'.` |

---

## Partie 3 — Exemple concret : Le Juge `chmod 444` d'un Analyste Fonctionnel / PO (`30 lignes Python`)

Pour montrer à un Analyste Fonctionnel ou un PO à quel point c'est simple : voici le script `judge_spec_ti.py` qu'on verrouille en `chmod 444`. Tant que la spec ou la User Story générée par l'IA ne valide pas ces 4 contrôles objectifs, l'IA **n'a pas le droit de s'arrêter** :

```python
#!/usr/bin/env python3
"""judge_spec_ti.py (chmod 444) — Juge déterministe pour Analyste Fonctionnel & PO."""
import re, sys
from pathlib import Path

FORBIDDEN_VAGUE_WORDS = ["tbd", "à définir", "etc.", "à préciser", "todo", "intuitif", "rapide"]
REQUIRED_SECTIONS = ["## Acteurs", "## Règles de Gestion", "## Critères d'Acceptation (Gherkin)", "## Cas d'Erreur"]

spec_path = Path(sys.argv[1])
text = spec_path.read_text(encoding="utf-8")
errors = []

# 1. Vérifier les sections obligatoires du template TI
for sec in REQUIRED_SECTIONS:
    if sec.lower() not in text.lower():
        errors.append(f"Section obligatoire manquante : `{sec}`")

# 2. Vérifier que chaque Règle de Gestion (RG-01, RG-02...) est couverte dans les scénarios Gherkin
rgs = set(re.findall(r"\bRG-\d{2,3}\b", text))
if not rgs:
    errors.append("Aucune Règle de Gestion numérotée (`RG-01`, `RG-02`...) n'a été définie.")
gherkin_part = text.lower().split("gherkin")[-1] if "gherkin" in text.lower() else ""
for rg in sorted(rgs):
    if rg.lower() not in gherkin_part:
        errors.append(f"La règle `{rg}` n'est couverte par aucun scénario Gherkin (Given/When/Then).")
if not all(k in gherkin_part for k in ("given ", "when ", "then ")) and not all(k in gherkin_part for k in ("soit ", "quand ", "alors ")):
    errors.append("Les critères d'acceptation ne respectent pas la structure Gherkin (Given/When/Then ou Soit/Quand/Alors).")

# 3. Chasser les mots flous qui créent des bugs en développement
for word in FORBIDDEN_VAGUE_WORDS:
    if re.search(rf"\b{re.escape(word)}\b", text.lower()):
        errors.append(f"Terme flou interdit dans une spec TI : `{word}` (spécifie la valeur ou le comportement exact).")

if errors:
    print("STOP HOOK AF/PO BLOQUÉ :\n- " + "\n- ".join(errors))
    sys.exit(1)
print("JUGE AF/PO (chmod 444) : OK — Spécification complète, traçable et sans ambiguïté.")
```
