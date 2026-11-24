#!/usr/bin/env python3
"""
Hook Claude Code PreToolUse — pre_tool_cuisine_guard.py
Applique en temps réel deux lois scientifiques avant chaque appel d'outil :
  1. Mode 5 Defense (Google arXiv:2611.22299) :
     Bloque toute tentative d'éditer, écraser ou `chmod` un fichier Juge (`judge_*.py`, `verify_gate.py`).
  2. Mode Cuisine & Réduction de Tokens (Prime Agent arXiv:2608.23552 + Meta-Harness arXiv:2603.28052) :
     Si l'agent tente un `Read` complet sur un fichier de données lourd (`.csv`, `.tsv`, `.jsonl`,
     `words.json`, `transcript.json`, `.lock`, ou `.json` > 35 Ko) sans `limit <= 60`,
     bloque l'aspiration en contexte L1 et renvoie directement l'aperçu schéma (~120 tokens) !
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS_ROOT / "core"))

from action_aci import HEAVY_DATA_EXTENSIONS, HEAVY_DATA_NAMES, is_protected_judge  # noqa: E402
from context_mgr import build_data_schema_preview  # noqa: E402


def deny(reason: str) -> int:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        event = json.loads(raw)
    except Exception:
        return 0

    tool_name = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") or {}
    cwd = Path(event.get("cwd") or ".").resolve()

    # 1. Protection Mode 5 sur Write / Edit / MultiEdit
    if tool_name in ("Write", "Edit", "MultiEdit"):
        fp_str = str(tool_input.get("file_path") or tool_input.get("path") or "")
        if fp_str:
            fpath = (cwd / fp_str).resolve() if not Path(fp_str).is_absolute() else Path(fp_str).resolve()
            if is_protected_judge(fpath):
                return deny(
                    f"[HARNAIS H2 — SÉCURITÉ MODE 5] Interdiction absolue de modifier le juge `{fpath.name}` "
                    f"(verrouillé en lecture seule chmod 444). Corrige ton code ou tes données, jamais l'évaluateur."
                )

    # 2. Protection Mode 5 sur Bash (interdire chmod/rm/redirection sur les juges)
    if tool_name == "Bash":
        cmd = str(tool_input.get("command") or "")
        if any(tok in cmd for tok in ("judge_code.py", "judge_data.py", "judge_video.py", "judges_sha256.json")):
            if any(op in cmd for op in ("chmod", "chown", "rm ", ">", "tee ", "sed -i")):
                return deny(
                    "[HARNAIS H2 — SÉCURITÉ MODE 5] Tentative de modifier les permissions ou le code d'un juge chmod 444 via Bash bloquée."
                )

    # 3. Mode Cuisine automatique sur Read de gros fichiers de données
    if tool_name == "Read":
        fp_str = str(tool_input.get("file_path") or "")
        limit = tool_input.get("limit")
        if fp_str and (limit is None or int(limit) > 60):
            fpath = (cwd / fp_str).resolve() if not Path(fp_str).is_absolute() else Path(fp_str).resolve()
            if fpath.exists() and fpath.is_file():
                sfx = fpath.suffix.lower()
                size = fpath.stat().st_size
                is_heavy_data = (
                    (sfx in HEAVY_DATA_EXTENSIONS and size > 4096)
                    or fpath.name in HEAVY_DATA_NAMES
                    or (sfx == ".json" and size > 35_000)
                )
                if is_heavy_data:
                    preview = build_data_schema_preview(fpath)
                    return deny(
                        f"[HARNAIS H2 — MODE CUISINE ACTIVÉ (Économie de tokens L1)]\n"
                        f"Lecture brute bloquée ({size // 1024} Ko). Voici le schéma L1 (~120 tokens) :\n\n"
                        f"{preview}\n\n"
                        f"👉 Pour interroger ou calculer sur ce fichier sans polluer ton contexte, utilise Python "
                        f"(`h2 query \"{fpath}\" \"...\"` ou un script Python) ou `Read` avec `limit: 40`."
                    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
