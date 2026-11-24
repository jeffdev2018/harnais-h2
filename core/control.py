#!/usr/bin/env python3
"""
Brique 1 & 4 — control.py (Google arXiv:2611.22299 + Harness-Bench arXiv:2605.27922)
Boucle de contrôle de l'agent :
  - Plafond de tours strict (12 tours par défaut, ajustable par profil modèle)
  - Détecteur de Doom-Loop (bloque si le modèle répète 3x le même appel (tool, args))
  - Parseur d'actions JSON tolérant
  - Sandwich de raisonnement (xhigh au cadrage/vérif, normal à l'exécution)
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MAX_TURNS = 12
DEFAULT_TOKEN_BUDGET = 110_000
MAX_IDENTICAL_CALLS = 2


@dataclass
class ControlState:
    max_turns: int = DEFAULT_MAX_TURNS
    token_budget: int = DEFAULT_TOKEN_BUDGET
    turn: int = 0
    used_tokens: int = 0
    edited_files: list[str] = field(default_factory=list)
    call_fingerprints: dict[str, int] = field(default_factory=dict)
    blocked_exits: int = 0

    def register_call(self, tool_name: str, args: dict[str, Any]) -> tuple[bool, str]:
        """Détecte les boucles infinies (Doom-Loop) sur (tool_name, args)."""
        raw = f"{tool_name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        fp = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        count = self.call_fingerprints.get(fp, 0) + 1
        self.call_fingerprints[fp] = count
        if count > MAX_IDENTICAL_CALLS:
            return (
                False,
                f"[CONTROL DOOM-LOOP BLOQUÉ] Tu as appelé `{tool_name}` avec exactement les mêmes "
                f"arguments {count} fois. Change d'approche ou inspecte l'erreur.",
            )
        return True, "OK"

    def reasoning_effort_for_turn(self) -> str:
        """
        Reasoning Sandwich (Harness Engineering / Huashu 2026) :
        Effort élevé au tour 1 (cadrage) et au dernier tour/vérif, effort standard entre les deux.
        """
        if self.turn <= 1 or self.turn >= self.max_turns - 1:
            return "high"
        return "medium"


def parse_agent_action(raw_response: str) -> dict[str, Any]:
    """Extrait l'appel d'outil JSON `{ "tool": ..., "args": ... }` de la réponse du modèle."""
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw_response, flags=re.DOTALL)
    candidates = fenced + [raw_response.strip()]
    for cand in candidates:
        start = cand.find("{")
        end = cand.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(cand[start : end + 1])
                if isinstance(obj, dict) and "tool" in obj:
                    return {"tool": str(obj["tool"]), "args": obj.get("args") or {}}
            except Exception:
                continue
    return {"tool": "finish", "args": {"summary": raw_response.strip()}}


def load_model_profile(model_name: str, profiles_path: Path | None = None) -> dict[str, Any]:
    """
    Harness-Bench (arXiv:2605.27922) : corrélation de rang -0.05 entre modèles.
    Charge les hyperparamètres fins adaptés au modèle sans alourdir le prompt.
    """
    default_profile = {
        "max_turns": DEFAULT_MAX_TURNS,
        "token_budget": DEFAULT_TOKEN_BUDGET,
        "obs_max_chars": 800,
        "keep_recent_turns": 2,
        "force_cuisine_python": True,
    }
    if profiles_path is None:
        profiles_path = Path(__file__).resolve().parent.parent / "profiles" / "model_profiles.json"
    if not profiles_path.exists():
        return default_profile
    try:
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
        key = model_name.lower()
        for pattern, cfg in profiles.items():
            if pattern in key:
                return {**default_profile, **cfg}
    except Exception:
        pass
    return default_profile
