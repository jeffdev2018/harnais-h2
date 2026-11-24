#!/usr/bin/env python3
"""
Brique 1 & 5 — action_aci.py (Google arXiv:2611.22299 + Pi 4-Tools Minimalist ACI)
Interface Agent-Ordinateur (ACI) réduite à 4 outils expressifs :
  1. view_file(path, start_line, end_line) — lecture fenêtrée (bloque le dump de gros CSV/JSON en L1)
  2. edit_file(path, target, replacement)  — édition chirurgicale (interdit de toucher aux juges chmod 444)
  3. bash(cmd, timeout)                    — exécution shell à sortie bornée + protection du juge
  4. finish(summary)                       — garde anti-sortie vide (bloque si aucun travail ou vérif absente)
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
try:
    from .context_mgr import build_data_schema_preview
except ImportError:
    from context_mgr import build_data_schema_preview

MAX_VIEW_LINES = 160
MAX_BASH_CHARS = 4000
HEAVY_DATA_EXTENSIONS = {".csv", ".tsv", ".jsonl", ".lock"}
HEAVY_DATA_NAMES = {"words.json", "transcript.json", "raea.lock", "package-lock.json", "pnpm-lock.yaml"}


def is_protected_judge(path: Path) -> bool:
    """Vérifie si un fichier est un évaluateur/juge protégé (Mode 5 Defense - chmod 444)."""
    name = path.name.lower()
    if "judge" in name or "verify_gate" in name or ".harness/judges" in str(path):
        return True
    if path.exists():
        mode = stat.S_IMODE(path.stat().st_mode)
        if not (mode & stat.S_IWUSR):  # Read-only file (e.g. chmod 444)
            return True
    return False


def view_file(path_str: str, start_line: int = 1, end_line: int = 120, workspace: Path | None = None) -> str:
    """Outil 1/4 : Lecture fenêtrée avec bascule automatique en Mode Cuisine sur gros fichiers."""
    root = workspace or Path.cwd()
    path = (root / path_str).resolve() if not Path(path_str).is_absolute() else Path(path_str).resolve()
    if not path.exists():
        return f"[ACI view_file ERREUR] Fichier introuvable : {path_str}"

    # Bascule automatique en Mode Cuisine si fichier de données lourd
    if (
        path.suffix.lower() in HEAVY_DATA_EXTENSIONS
        or path.name in HEAVY_DATA_NAMES
        or (path.suffix.lower() == ".json" and path.stat().st_size > 25_000)
    ):
        return build_data_schema_preview(path)

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    s = max(1, start_line)
    e = min(len(lines), min(end_line, s + MAX_VIEW_LINES - 1))
    numbered = [f"{i:4d}: {lines[i - 1]}" for i in range(s, e + 1)]
    header = f"[ACI view_file] `{path.name}` (lignes {s}..{e} sur {len(lines)}) :"
    return header + "\n" + "\n".join(numbered)


def edit_file(
    path_str: str,
    target: str,
    replacement: str,
    edited_files: list[str],
    workspace: Path | None = None,
) -> str:
    """Outil 2/4 : Édition de fichier avec protection matérielle contre l'altération du juge."""
    root = workspace or Path.cwd()
    path = (root / path_str).resolve() if not Path(path_str).is_absolute() else Path(path_str).resolve()

    if is_protected_judge(path):
        return (
            f"[ACI SECURITÉ MODE 5 BLOQUÉ] Interdiction absolue de modifier l'évaluateur/juge "
            f"`{path.name}` (lecture seule chmod 444). Corrige ton code, pas le test."
        )

    if not path.exists():
        if target:
            return f"[ACI edit_file ERREUR] `{path_str}` n'existe pas (laisse target vide pour créer)."
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(replacement, encoding="utf-8")
        if path_str not in edited_files:
            edited_files.append(path_str)
        return f"[ACI edit_file OK] Fichier créé : `{path_str}` ({len(replacement)} octets)."

    content = path.read_text(encoding="utf-8")
    if target not in content:
        return f"[ACI edit_file ERREUR] Segment `target` introuvable dans `{path_str}`. Relis les lignes exactes."

    updated = content.replace(target, replacement, 1)
    path.write_text(updated, encoding="utf-8")
    if path_str not in edited_files:
        edited_files.append(path_str)
    return f"[ACI edit_file OK] `{path_str}` mis à jour."


def bash(cmd: str, workspace: Path | None = None, timeout: int = 30) -> str:
    """Outil 3/4 : Exécution shell bornée avec interdiction de contourner chmod 444."""
    forbidden_patterns = ["chmod ", "chown ", "verify_gate.py", "judge_"]
    if any(p in cmd and ("chmod" in cmd or "rm " in cmd or ">" in cmd) for p in forbidden_patterns):
        return "[ACI SECURITÉ MODE 5 BLOQUÉ] Tentative de modification des permissions ou des juges refusée."

    root = workspace or Path.cwd()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        out = (proc.stdout or "") + ("\n[STDERR]\n" + proc.stderr if proc.stderr else "")
        out = out.strip()
        if len(out) > MAX_BASH_CHARS:
            half = MAX_BASH_CHARS // 2
            out = f"{out[:half]}\n... [sortie bash tronquée à {MAX_BASH_CHARS} car.] ...\n{out[-half:]}"
        return f"[ACI bash exit={proc.returncode}]\n{out}"
    except subprocess.TimeoutExpired:
        return f"[ACI bash TIMEOUT] Commande interrompue après {timeout}s."


def finish(summary: str, edited_files: list[str], require_edits: bool = True) -> tuple[bool, str]:
    """Outil 4/4 : Signal de fin avec garde empty-diff (Google 2611.22299 §VII)."""
    if require_edits and not edited_files:
        return (
            False,
            "[ACI finish BLOQUÉ : EMPTY-DIFF GUARD] Tu appelles `finish` alors qu'aucun fichier ou "
            "résultat n'a été produit/édité. Exécute le travail avant de terminer.",
        )
    return True, summary
