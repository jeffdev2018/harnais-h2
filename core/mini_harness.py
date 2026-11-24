#!/usr/bin/env python3
"""
Brique 1..5 Assemblées — mini_harness.py (Squelette complet ~140 lignes de Google arXiv:2611.22299)
Assemble les 4 modules :
  1. context_mgr.py (AGENTS.md <= 12 lignes, aperçu Mode Cuisine L1, compaction Head-Tail, footer live)
  2. control.py     (plafond 12 tours, anti-doom-loop, profil par modèle, sandwich de raisonnement)
  3. action_aci.py  (4 outils Pi : view_file, edit_file, bash, finish + protection Juge chmod 444)
  4. verify.py      (Stop Hook déterministe pré-arrêt + vérification SHA-256 des juges read-only)

Peut s'utiliser :
  - En vérification autonome : `python3 mini_harness.py --verify-only [--domain auto|code|data|video]`
  - En aperçu Mode Cuisine   : `python3 mini_harness.py --peek <fichier.csv|words.json>`
  - En exécution d'agent     : `python3 mini_harness.py --task "Analyse..." --data fichier.csv`
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from action_aci import bash, edit_file, finish, view_file
from context_mgr import build_data_schema_preview, compact_history, load_lean_agents_md
from control import ControlState, load_model_profile, parse_agent_action
from verify import run_pre_stop_verifier

HARNESS_ROOT = Path(__file__).resolve().parent.parent


def build_system_prompt(workspace: Path, domain: str, data_files: list[Path] | None = None) -> str:
    """Construit le prompt système minimaliste (AGENTS.md <= 12 lignes + contrat 4 outils JSON)."""
    agents_md = load_lean_agents_md(workspace / "AGENTS.md") or load_lean_agents_md(HARNESS_ROOT / "AGENTS.md")
    previews = "\n\n".join(build_data_schema_preview(p) for p in (data_files or []))
    return (
        f"{agents_md}\n\n"
        f"Domaine actif : {domain.upper()}. Réponds UNIQUEMENT par un objet JSON d'appel d'outil parmi ces 4 outils :\n"
        f'1. {{"tool": "view_file", "args": {{"path": "...", "start_line": 1, "end_line": 120}}}}\n'
        f'2. {{"tool": "edit_file", "args": {{"path": "...", "target": "...", "replacement": "..."}}}}\n'
        f'3. {{"tool": "bash", "args": {{"cmd": "..."}}}}\n'
        f'4. {{"tool": "finish", "args": {{"summary": "..."}}}}\n'
        + (f"\nDonnées disponibles en Mode Cuisine (L3) :\n{previews}\n" if previews else "")
    )


def run_agent_loop(
    task: str,
    llm_call: Callable[[list[dict[str, str]], str], tuple[str, int]],
    workspace: Path,
    model_name: str = "claude-sonnet",
    domain: str = "auto",
    data_files: list[Path] | None = None,
) -> dict[str, object]:
    """
    Boucle d'exécution Inner Loop (Fig. 1 gauche de Google arXiv:2611.22299) :
    Context & State -> Agent Control -> Action Interface -> Verification & Recovery.
    """
    profile = load_model_profile(model_name)
    state = ControlState(
        max_turns=int(profile["max_turns"]),
        token_budget=int(profile["token_budget"]),
    )
    sys_prompt = build_system_prompt(workspace, domain, data_files)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": task},
    ]

    for turn in range(1, state.max_turns + 1):
        state.turn = turn
        compacted = compact_history(
            messages,
            turn=turn,
            max_turns=state.max_turns,
            edited_files=state.edited_files,
            used_tokens=state.used_tokens,
            token_budget=state.token_budget,
            keep_recent_turns=int(profile["keep_recent_turns"]),
            max_chars=int(profile["obs_max_chars"]),
        )
        effort = state.reasoning_effort_for_turn()
        raw_reply, tokens = llm_call(compacted, effort)
        state.used_tokens += tokens
        messages.append({"role": "assistant", "content": raw_reply})

        action = parse_agent_action(raw_reply)
        tool = action["tool"]
        args = action["args"]

        ok_loop, loop_msg = state.register_call(tool, args)
        if not ok_loop:
            messages.append({"role": "user", "content": loop_msg})
            continue

        if tool == "view_file":
            obs = view_file(
                str(args.get("path", "")),
                int(args.get("start_line", 1)),
                int(args.get("end_line", 120)),
                workspace=workspace,
            )
        elif tool == "edit_file":
            obs = edit_file(
                str(args.get("path", "")),
                str(args.get("target", "")),
                str(args.get("replacement", "")),
                edited_files=state.edited_files,
                workspace=workspace,
            )
        elif tool == "bash":
            obs = bash(str(args.get("cmd", "")), workspace=workspace)
        elif tool == "finish":
            ok_fin, fin_msg = finish(
                str(args.get("summary", "")),
                edited_files=state.edited_files,
                require_edits=bool(profile.get("require_edits", True)),
            )
            if not ok_fin:
                state.blocked_exits += 1
                messages.append({"role": "user", "content": fin_msg})
                continue

            # Porte de vérification pré-arrêt (Module 4 : verify.py + Juges chmod 444)
            ok_ver, ver_errors = run_pre_stop_verifier(
                workspace=workspace,
                edited_files=state.edited_files,
                domain=domain,
            )
            if not ok_ver:
                state.blocked_exits += 1
                err_report = "\n".join(ver_errors)
                messages.append(
                    {
                        "role": "user",
                        "content": f"[STOP HOOK VERIFY_GATE BLOQUÉ]\n{err_report}\nCorrige ces erreurs avant d'appeler `finish`.",
                    }
                )
                continue

            return {
                "status": "completed",
                "turns": turn,
                "used_tokens": state.used_tokens,
                "blocked_exits": state.blocked_exits,
                "edited_files": state.edited_files,
                "summary": fin_msg,
            }
        else:
            obs = f"[ACI ERREUR] Outil inconnu `{tool}`. Utilise uniquement view_file, edit_file, bash, finish."

        messages.append({"role": "user", "content": obs})

    return {
        "status": "max_turns_exhausted",
        "turns": state.max_turns,
        "used_tokens": state.used_tokens,
        "blocked_exits": state.blocked_exits,
        "edited_files": state.edited_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mini-Harnais H2 (4 modules Google 2611.22299 + Mode Cuisine RLM)")
    parser.add_argument("--workspace", default=".", help="Répertoire de travail")
    parser.add_argument("--domain", default="auto", choices=["auto", "code", "data", "cuisine", "video"])
    parser.add_argument("--verify-only", action="store_true", help="Exécute uniquement le Stop Hook et les juges 444")
    parser.add_argument("--peek", help="Affiche l'aperçu Mode Cuisine L1 (~120 tokens) d'un fichier lourd")
    parser.add_argument("files", nargs="*", help="Fichiers optionnels à vérifier")
    args = parser.parse_args()

    ws = Path(args.workspace).resolve()
    if args.peek:
        print(build_data_schema_preview((ws / args.peek).resolve()))
        return 0

    ok, errors = run_pre_stop_verifier(ws, edited_files=args.files or None, domain=args.domain)
    if ok:
        print("HARNAIS H2 VERIFY: OK (Juges chmod 444 + Syntaxe + Livrables validés)")
        return 0
    print("\n".join(errors))
    return 1


if __name__ == "__main__":
    sys.exit(main())
