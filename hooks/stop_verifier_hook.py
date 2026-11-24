#!/usr/bin/env python3
"""
Hook Claude Code Stop — stop_verifier_hook.py (Google arXiv:2611.22299 Pre-Stop Verifier)
Exécuté automatiquement quand l'agent tente de terminer son tour :
  1. Évite toute boucle infinie : si `stop_hook_active` est True, laisse passer après 1 relance.
  2. Vérifie l'intégrité des Juges read-only (chmod 444 + SHA-256).
  3. Inspecte uniquement les fichiers modifiés dans la session/repo (`git status --porcelain`).
  4. Si un fichier modifié a une erreur de syntaxe, un JSON cassé, un média vide ou un pattern de triche,
     bloque l'arrêt (`{"decision": "block", "reason": ...}`), journalise l'échec et déclenche l'Outer Loop !
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS_ROOT / "core"))
sys.path.insert(0, str(HARNESS_ROOT / "evolve"))

from modular_evolver import record_verifier_block, run_evolution_cycle  # noqa: E402
from verify import run_pre_stop_verifier  # noqa: E402


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}

    # Garde-fou anti-boucle infinie si Claude Code est déjà dans un cycle de réparation Stop Hook
    if event.get("stop_hook_active") is True:
        return 0

    cwd = Path(event.get("cwd") or ".").resolve()
    ok, errors = run_pre_stop_verifier(workspace=cwd, domain="auto")
    if ok:
        return 0

    # Journalise le blocage dans l'Outer Loop et met à jour les SKILL.md récursifs si erreur répétée
    try:
        record_verifier_block(domain="auto", errors=errors, workspace=str(cwd))
        run_evolution_cycle(min_occurrences=2)
    except Exception:
        pass

    reason = (
        "[HARNAIS H2 — STOP HOOK VÉRIFICATEUR (Google 2611.22299)]\n"
        "Arrêt refusé par le juge déterministe (chmod 444) :\n- "
        + "\n- ".join(errors)
        + "\n\nCorrige ces points puis vérifie avec `h2 verify` avant de terminer."
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
