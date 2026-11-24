#!/usr/bin/env python3
"""
Brique 1 & 4 (v2) — modular_evolver.py
Sources :
  - Google arXiv:2611.22299 : Outer Loop Modular Gated Evolution + Table III.A.3 (Securing Persistent Memory)
  - Prime Agent arXiv:2608.23552 §2.5 : Continual Harness (Provenance, Versioning & Rollback)
  - RRSI / SoL-Pi arXiv:2611.22299 [20, 42] : Pareto Token-Budget Gate on learned skills

Cycle d'auto-amélioration sécurisé en 4 étapes :
  - Stage 1 (Diagnose & Quarantine) : les erreurs observées 1x vont en quarantaine (`quarantine_patches.json`)
                                      avec traçabilité de provenance (évite le Mode 1 Single-Run Reflection Bloat)
  - Stage 2 (Propose Edits)         : synthétise un patch d'UNE ligne pour le SKILL.md du domaine
  - Stage 3 (Validate, Sanitize & Token Gate) :
      * Vérifie l'intégrité des juges chmod 444 (Mode 5)
      * Sanitizer Anti-Injection (Table III.A.3 : bloque toute règle contenant des commandes shell, URLs, ou
        affaiblissement de sécurité type verify=False)
      * Plafond de budget tokens par SKILL.md (<= 450 tokens / 12 patches max)
  - Stage 4 (Deploy with Version Snapshot & Rollback) :
      * Sauvegarde une version horodatée dans `logs/skill_versions/` avant d'écrire (permet `h2 rollback`)
"""
from __future__ import annotations

import collections
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = HARNESS_ROOT / "logs" / "verifier_blocks.jsonl"
QUARANTINE_PATH = HARNESS_ROOT / "logs" / "quarantine_patches.json"
VERSIONS_DIR = HARNESS_ROOT / "logs" / "skill_versions"
SKILLS_DIR = HARNESS_ROOT / "skills"
JUDGES_DIR = HARNESS_ROOT / "judges"

MAX_SKILL_TOKENS = 450
MAX_SKILL_PATCHES = 12
POISON_PATTERNS = (
    "curl ",
    "wget ",
    "http://",
    "https://",
    "verify=False",
    "chmod 777",
    "chmod 666",
    "rm -rf",
    "eval(",
    "base64",
)

sys.path.insert(0, str(HARNESS_ROOT / "core"))
from verify import check_judge_integrity  # noqa: E402


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def record_verifier_block(domain: str, errors: list[str], workspace: str, used_tokens: int = 0) -> None:
    """Enregistre en append-only chaque arrêt bloqué par le Stop Hook avec provenance complète."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "domain": domain,
        "workspace": workspace,
        "used_tokens": used_tokens,
        "errors": errors,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def stage1_diagnose_failures(min_occurrences: int = 2) -> tuple[list[tuple[str, str, int]], list[dict[str, object]]]:
    """
    Stage 1 : Sépare les erreurs récurrentes (>= min_occurrences -> candidates à promotion)
    des erreurs isolées (1x -> mises en quarantaine selon Google 2611.22299 Table II Mode 1).
    """
    if not LOG_PATH.exists():
        return [], []
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    last_ws: dict[tuple[str, str], str] = {}
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            dom = row.get("domain", "code")
            ws = row.get("workspace", ".")
            for err in row.get("errors", []):
                sig = err.split("\n")[0].strip()[:140]
                counts[(dom, sig)] += 1
                last_ws[(dom, sig)] = ws
        except Exception:
            continue

    promoted_candidates = []
    quarantined = []
    for (dom, sig), c in counts.most_common(20):
        if c >= min_occurrences:
            promoted_candidates.append((dom, sig, c))
        else:
            quarantined.append(
                {
                    "domain": dom,
                    "error_signature": sig,
                    "occurrences": c,
                    "status": "quarantine_awaiting_repeat",
                    "provenance_workspace": last_ws.get((dom, sig), "."),
                }
            )

    QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE_PATH.write_text(json.dumps(quarantined, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return promoted_candidates, quarantined


def stage2_propose_skill_patch(domain: str, error_sig: str) -> tuple[Path, str]:
    """Stage 2 : Synthétise une règle 'Do-Not / Must' courte d'une seule ligne pour le SKILL.md ciblé."""
    dom_map = {
        "data": "cuisine-data",
        "cuisine": "cuisine-data",
        "video": "video-studio",
        "code": "pi-code",
        "auto": "pi-code",
    }
    if "MODE 4" in error_sig or "décimales" in error_sig or "JSON" in error_sig:
        skill_folder = "cuisine-data"
    elif "GUI-HARVEST" in error_sig or "Média" in error_sig or "ffprobe" in error_sig:
        skill_folder = "video-studio"
    else:
        skill_folder = dom_map.get(domain, "pi-code")

    skill_file = SKILLS_DIR / skill_folder / "SKILL.md"

    if "SYNTAXE PYTHON" in error_sig or "py_compile" in error_sig:
        rule = "Toujours lancer `python3 -m py_compile <fichier.py>` avant de conclure."
    elif "MODE 4" in error_sig or "ANTI-HARDCODING" in error_sig:
        rule = "Interdiction de coder en dur un résultat : le script doit ouvrir le fichier source et boucler sur les lignes."
    elif "plus de 2 décimales" in error_sig or "Decimal" in error_sig:
        rule = "Arrondir chaque montant monétaire avec `Decimal(str(x)).quantize(Decimal('0.01'), ROUND_HALF_UP)`."
    elif "GUI-HARVEST" in error_sig or "ÉCRAN NOIR" in error_sig:
        rule = "Vérifier que le rendu `.mp4` n'est pas un écran noir (`ffmpeg blackdetect`) avant de valider."
    elif "Média" in error_sig or "ffprobe" in error_sig:
        rule = "Vérifier tout fichier `.mp4`/`.wav` avec `ffprobe` (taille > 10 Ko, durée > 0.5s) avant d'arrêter."
    elif "JSON invalide" in error_sig or "null" in error_sig:
        rule = "Valider la sortie finale avec `json.loads` et vérifier l'absence de `null`/`NaN` avant `finish`."
    elif "MODE 5" in error_sig:
        rule = "Ne jamais tenter d'éditer ou de changer les permissions (`chmod`) d'un fichier `judge_*.py`."
    else:
        clean_sig = re.sub(r"[^a-zA-Z0-9À-ÿ _.,:/()-]", "", error_sig.replace("VERIFY_GATE", "")).strip(" :[]")
        rule = f"Éviter l'erreur récurrente : {clean_sig[:100]}"

    return skill_file, rule


def stage3_validate_patch(skill_file: Path, proposed_rule: str) -> tuple[bool, str]:
    """
    Stage 3 (Validation, Security Sanitizer & Token Budget Gate) :
    - Vérifie que les juges chmod 444 sont intacts
    - Bloque toute règle suspecte d'injection mémoire (Google 2611.22299 Table III.A.3)
    - Vérifie le plafond de tokens du SKILL.md (<= 450 tokens)
    """
    ok_j, msg_j = check_judge_integrity(JUDGES_DIR)
    if not ok_j:
        return False, f"Stage 3 Rejet : {msg_j}"

    low_rule = proposed_rule.lower()
    for poison in POISON_PATTERNS:
        if poison.lower() in low_rule:
            return False, f"Stage 3 Rejet [SÉCURITÉ MÉMOIRE TABLE III.A.3] : Pattern interdit `{poison}` dans la règle."

    if not skill_file.exists():
        return False, f"Stage 3 Rejet : `{skill_file}` introuvable."

    content = skill_file.read_text(encoding="utf-8")
    if proposed_rule in content:
        return False, "Stage 3 Rejet : Patch déjà présent dans le SKILL.md (zéro doublon)."

    existing_patches = [ln for ln in content.splitlines() if ln.strip().startswith("- `[Patch #")]
    if len(existing_patches) >= MAX_SKILL_PATCHES:
        return False, f"Stage 3 Rejet : Plafond de {MAX_SKILL_PATCHES} patches atteint (anti-prompt-bloat)."

    projected_tokens = estimate_tokens(content + "\n" + proposed_rule)
    if projected_tokens > MAX_SKILL_TOKENS:
        return (
            False,
            f"Stage 3 Rejet [BUDGET TOKENS] : `{skill_file.parent.name}/SKILL.md` dépasserait "
            f"{MAX_SKILL_TOKENS} tokens ({projected_tokens} tok).",
        )

    return True, f"Stage 3 Validé (Patch #{len(existing_patches) + 1}, {projected_tokens}/{MAX_SKILL_TOKENS} tokens)"


def stage4_deploy_patch(skill_file: Path, proposed_rule: str) -> str:
    """Stage 4 : Sauvegarde un snapshot versionné (Continual Harness §2.5) puis déploie le patch."""
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = VERSIONS_DIR / f"{skill_file.parent.name}_SKILL_{ts}.md.bak"
    shutil.copy2(skill_file, snap)

    content = skill_file.read_text(encoding="utf-8").rstrip()
    existing_patches = [ln for ln in content.splitlines() if ln.strip().startswith("- `[Patch #")]
    next_id = len(existing_patches) + 1
    patch_line = f"- `[Patch #{next_id}]` {proposed_rule}"
    skill_file.write_text(content + "\n" + patch_line + "\n", encoding="utf-8")
    return patch_line


def rollback_skill(skill_domain: str) -> int:
    """Restaure la dernière version sauvegardée d'un SKILL.md (Continual Harness §2.5 Rollback)."""
    if not VERSIONS_DIR.exists():
        print("[EVOLVER ROLLBACK] Aucun snapshot disponible.")
        return 1
    snaps = sorted(VERSIONS_DIR.glob(f"{skill_domain}_SKILL_*.md.bak"))
    if not snaps:
        print(f"[EVOLVER ROLLBACK] Aucun snapshot pour `{skill_domain}`.")
        return 1
    latest = snaps[-1]
    target = SKILLS_DIR / skill_domain / "SKILL.md"
    shutil.copy2(latest, target)
    latest.unlink()
    print(f"[EVOLVER ROLLBACK OK] `{skill_domain}/SKILL.md` restauré depuis `{latest.name}`.")
    return 0


def prune_all_skills() -> int:
    """
    Brique v4.4 — Élagage Automatique & Hygiène de Portée (`h2 prune`)
    Sources : Anthropic (Harness-as-Assumption) & Google arXiv:2611.22299 Table II Mode 1 & Table III.B.3
    Inspecte tous les `skills/*/SKILL.md` :
      1. Supprime les règles `[Patch #N]` en doublon ou contenant un pattern toxique.
      2. Vérifie que chaque règle `[Patch #N]` possède une condition de déclenchement explicite
         `(UNIQUEMENT SI ...)` pour empêcher la sur-généralisation sur les tâches simples (Mode 1).
      3. Élagage au plafond de budget tokens (<= 450 tokens par SKILL.md).
    """
    pruned_count = 0
    scoped_count = 0
    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        lines = skill_file.read_text(encoding="utf-8").splitlines()
        header_lines: list[str] = []
        patch_bodies: list[str] = []
        seen_bodies: set[str] = set()
        modified = False

        for ln in lines:
            s = ln.strip()
            if s.startswith("- `[Patch #"):
                body = re.sub(r"^-\s*`\[Patch\s*#\d+\]`\s*", "", s).strip()
                # 1. Filtrer doublons et règles toxiques
                norm_key = body.lower()
                if norm_key in seen_bodies or any(p.lower() in norm_key for p in POISON_PATTERNS):
                    pruned_count += 1
                    modified = True
                    continue
                seen_bodies.add(norm_key)

                # 2. Garantir le cadrage conditionnel (Mode 1 Anti-Overgeneralization)
                if not body.upper().startswith("(UNIQUEMENT"):
                    if ":" in body:
                        topic, _, rest = body.partition(":")
                        body = f"(UNIQUEMENT SI la tâche concerne {topic.strip()}) : {rest.strip()}"
                    else:
                        body = f"(UNIQUEMENT SI applicable à la consigne) : {body}"
                    scoped_count += 1
                    modified = True
                patch_bodies.append(body)
            else:
                header_lines.append(ln)

        # 3. Respect du plafond MAX_SKILL_PATCHES et MAX_SKILL_TOKENS
        while len(patch_bodies) > MAX_SKILL_PATCHES:
            patch_bodies.pop(0)
            pruned_count += 1
            modified = True

        rebuilt_patches = [f"- `[Patch #{i + 1}]` {b}" for i, b in enumerate(patch_bodies)]
        new_content = "\n".join(header_lines + rebuilt_patches).rstrip() + "\n"

        while estimate_tokens(new_content) > MAX_SKILL_TOKENS and len(patch_bodies) > 1:
            patch_bodies.pop(0)
            pruned_count += 1
            modified = True
            rebuilt_patches = [f"- `[Patch #{i + 1}]` {b}" for i, b in enumerate(patch_bodies)]
            new_content = "\n".join(header_lines + rebuilt_patches).rstrip() + "\n"

        if modified:
            VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            shutil.copy2(skill_file, VERSIONS_DIR / f"{skill_file.parent.name}_SKILL_{ts}.md.bak")
            skill_file.write_text(new_content, encoding="utf-8")

        tok = estimate_tokens(new_content)
        print(
            f"  • {skill_file.parent.name:20s} : {len(patch_bodies):2d} patch(es) actifs | "
            f"{tok:3d}/{MAX_SKILL_TOKENS} tokens | 100% conditionnels (UNIQUEMENT SI)"
        )

    print(f"[H2 PRUNE TERMINÉ] {pruned_count} règle(s) élaguée(s), {scoped_count} règle(s) recadrée(s) avec condition.")
    return 0


def run_evolution_cycle(min_occurrences: int = 2) -> int:
    clusters, quarantined = stage1_diagnose_failures(min_occurrences=min_occurrences)
    if quarantined:
        print(f"[EVOLVER STAGE 1] {len(quarantined)} erreur(s) isolée(s) maintenue(s) en quarantaine (`logs/quarantine_patches.json`).")
    if not clusters:
        print(f"[EVOLVER] Aucun échec récurrent (>= {min_occurrences}x) à promouvoir.")
        return 0

    for domain, err_sig, count in clusters:
        skill_file, rule = stage2_propose_skill_patch(domain, err_sig)
        ok, reason = stage3_validate_patch(skill_file, rule)
        if ok:
            line = stage4_deploy_patch(skill_file, rule)
            print(f"[EVOLVER PROMU -> {skill_file.parent.name}/SKILL.md (observé {count}x) | {reason}] {line}")
        else:
            print(f"[EVOLVER IGNORÉ ({domain})] {reason}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        dom = sys.argv[2] if len(sys.argv) > 2 else "cuisine-data"
        sys.exit(rollback_skill(dom))
    if len(sys.argv) > 1 and sys.argv[1] == "prune":
        sys.exit(prune_all_skills())
    min_occ = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    sys.exit(run_evolution_cycle(min_occurrences=min_occ))
