#!/usr/bin/env python3
"""
Hook Claude Code PostToolUse — post_tool_intermediate_check.py
Sources :
  - Zhang et al. (arXiv:2610.34577) : "Rethinking Verification in Agent Harnesses"
  - Vestrum (Google arXiv:2611.22299 Table I.D [37]) : Intermediate step verification stops error compounding

Pourquoi ce hook change tout :
  Au lieu d'attendre le `Stop Hook` final (tour 12) pour découvrir qu'un fichier édité au tour 2 contient
  une erreur de syntaxe Python/JS, un JSON invalide ou un calcul codé en dur (Mode 4), ce hook vérifie
  en <40ms chaque fichier dès qu'il est touché par `Write`, `Edit` ou `MultiEdit`.
  En cas d'erreur, il injecte immédiatement le diagnostic pour que l'agent corrige au tour suivant !
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS_ROOT / "core"))

from verify import verify_single_file_fast  # noqa: E402


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        event = json.loads(raw)
    except Exception:
        return 0

    tool_name = str(event.get("tool_name", ""))
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return 0

    tool_input = event.get("tool_input") or {}
    cwd = Path(event.get("cwd") or ".").resolve()
    fp_str = str(tool_input.get("file_path") or tool_input.get("path") or "")
    if not fp_str:
        return 0

    fpath = (cwd / fp_str).resolve() if not Path(fp_str).is_absolute() else Path(fp_str).resolve()
    errs = verify_single_file_fast(fpath, fp_str)
    if not errs:
        return 0

    msg = (
        "[HARNAIS H2 — VÉRIFICATION INTERMÉDIAIRE (arXiv:2610.34577)]\n"
        "Erreur détectée immédiatement après ton édition :\n- "
        + "\n- ".join(errs)
        + "\n👉 Corrige ce fichier immédiatement avant de passer à la suite."
    )
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": msg,
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": msg,
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
