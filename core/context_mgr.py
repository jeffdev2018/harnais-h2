#!/usr/bin/env python3
"""
Brique 1 & 3 (v2) — context_mgr.py
Sources :
  - Google arXiv:2611.22299 (§V [33] Chunked Prefix-Preserving Compaction)
  - Stanford Meta-Harness arXiv:2603.28052 (4x token reduction via programmatic schema preview)
  - Zha et al. arXiv:2611.03223 & ContextEcho arXiv:2606.17016 (Rule Compliance Anchor after Compaction)

Améliorations v2 :
  1. Chunked Prefix-Preserving Compaction : compacte par paliers de `chunk_size=4` messages pour ne pas
     invalider le KV-Cache de préfixe à chaque tour (évite la pénalité O(N^2) de recalcul du préfixe).
  2. ContextEcho Rule Anchor : ré-injecte en fin de contexte les 3 invariants critiques après compaction
     pour éliminer l'oubli des règles ("Rule Drift / Instruction Fade-Out", arXiv:2611.03223).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_AGENTS_MD_LINES = 12
OLD_OBS_MAX_CHARS = 800
KEEP_RECENT_TURNS = 2
CACHE_CHUNK_ALIGNMENT = 4

CONTEXT_ECHO_ANCHOR = (
    "[CONTEXT-ECHO ANCHOR (arXiv:2611.03223)] Invariants actifs : "
    "(1) Mode Cuisine L2 Python (Decimal ROUND_HALF_UP, zéro calcul mental/hardcodé) · "
    "(2) Juges chmod 444 intouchables (Mode 5) · "
    "(3) Vérification déterministe `h2 verify` obligatoire avant arrêt."
)


def load_lean_agents_md(path: Path) -> str:
    """Charge AGENTS.md en refusant l'inflation de règles (>12 lignes utiles)."""
    if not path.exists():
        return ""
    raw_lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return "\n".join(raw_lines[:MAX_AGENTS_MD_LINES])


def build_data_schema_preview(file_path: Path, sample_rows: int = 2) -> str:
    """
    Mode Cuisine (Prime Agent arXiv:2608.23552) :
    Laisse la donnée brute sur le disque (L3) et n'injecte en contexte actif (L1)
    que le schéma + 2 lignes d'exemple (~120 tokens au lieu de 40 000).
    """
    if not file_path.exists():
        return f"[ERREUR] Fichier introuvable : {file_path}"

    size_kb = file_path.stat().st_size / 1024.0
    suffix = file_path.suffix.lower()

    if suffix in (".csv", ".tsv"):
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        head = "\n".join(lines[: 1 + sample_rows])
        total_rows = max(0, len(lines) - 1)
        return (
            f"[MODE CUISINE L1] `{file_path.name}` ({total_rows} lignes, {size_kb:.1f} Ko sur disque L3).\n"
            f"Ne JAMAIS charger ce fichier en entier dans le chat. Traite-le via script Python (`h2 query` / `h2 run`).\n"
            f"Aperçu schéma (en-tête + {sample_rows} lignes) :\n```csv\n{head}\n```"
        )

    if suffix in (".json", ".jsonl"):
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".jsonl":
            lines = [ln for ln in raw.splitlines() if ln.strip()]
            sample = "\n".join(lines[:sample_rows])[:600]
            return (
                f"[MODE CUISINE L1] `{file_path.name}` ({len(lines)} entrées JSONL, {size_kb:.1f} Ko sur disque L3).\n"
                f"Extrait des {sample_rows} premières entrées :\n```json\n{sample}\n```"
            )
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                preview = json.dumps(data[:sample_rows], ensure_ascii=False, indent=2)[:600]
                return (
                    f"[MODE CUISINE L1] `{file_path.name}` (Liste JSON de {len(data)} éléments, {size_kb:.1f} Ko).\n"
                    f"Aperçu des {sample_rows} premiers éléments :\n```json\n{preview}\n```"
                )
            if isinstance(data, dict):
                keys = list(data.keys())
                sample_dict = {
                    k: (f"<list len={len(v)}>" if isinstance(v, list) else v)
                    for k, v in list(data.items())[:6]
                }
                preview = json.dumps(sample_dict, ensure_ascii=False, indent=2)[:600]
                return (
                    f"[MODE CUISINE L1] `{file_path.name}` (Objet JSON clés={keys[:12]}, {size_kb:.1f} Ko).\n"
                    f"Aperçu structure :\n```json\n{preview}\n```"
                )
        except Exception:
            pass

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    head = "\n".join(lines[:10])[:600]
    return (
        f"[MODE CUISINE L1] `{file_path.name}` ({len(lines)} lignes, {size_kb:.1f} Ko sur disque L3).\n"
        f"Premières lignes :\n```\n{head}\n```"
    )


def head_tail_compact(text: str, max_chars: int = OLD_OBS_MAX_CHARS) -> str:
    """Compaction Head-Tail (Google 2611.22299 §VII) pour les observations anciennes."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    omitted = len(text) - max_chars
    return f"{text[:half]}\n... [{omitted} caractères compactés par context_mgr] ...\n{text[-half:]}"


def compact_history(
    messages: list[dict[str, Any]],
    turn: int,
    max_turns: int,
    edited_files: list[str],
    used_tokens: int = 0,
    token_budget: int = 110_000,
    keep_recent_turns: int = KEEP_RECENT_TURNS,
    max_chars: int = OLD_OBS_MAX_CHARS,
    chunk_align: int = CACHE_CHUNK_ALIGNMENT,
) -> list[dict[str, Any]]:
    """
    Compaction alignée par blocs (KV-Cache friendly) + ContextEcho Rule Anchor (arXiv:2611.03223).
    """
    raw_cutoff = max(1, len(messages) - keep_recent_turns * 2)
    # Alignement par paliers de `chunk_align` messages pour stabiliser le préfixe KV-cache
    cutoff = max(1, (raw_cutoff // chunk_align) * chunk_align) if raw_cutoff >= chunk_align else 1

    compaction_triggered = False
    compacted: list[dict[str, Any]] = []
    for idx, msg in enumerate(messages):
        content = str(msg.get("content", ""))
        if 0 < idx < cutoff and len(content) > max_chars:
            compacted.append({**msg, "content": head_tail_compact(content, max_chars=max_chars)})
            compaction_triggered = True
        else:
            compacted.append(dict(msg))

    if compacted and compacted[-1].get("role") in ("user", "tool"):
        pct = (used_tokens / token_budget * 100.0) if token_budget else 0.0
        warn = " ⚠️ SMART ZONE >70% : finalise et vérifie !" if pct >= 70.0 else ""
        edits_str = ", ".join(edited_files) if edited_files else "aucun"
        echo = f"\n{CONTEXT_ECHO_ANCHOR}" if (compaction_triggered or turn >= 4 or pct >= 50.0) else ""
        footer = (
            f"{echo}\n[STATUS HARNAIS H2 v2 | Tour {turn}/{max_turns} | "
            f"Fichiers édités: {edits_str} | Tokens: {used_tokens:,}/{token_budget:,} ({pct:.0f}%){warn}]"
        )
        compacted[-1]["content"] = str(compacted[-1].get("content", "")) + footer
    return compacted
