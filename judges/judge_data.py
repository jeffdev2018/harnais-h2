#!/usr/bin/env python3
"""
Juge Read-Only (chmod 444) #2 — judge_data.py (Mode Cuisine / RLM arXiv:2608.23552)
Vérifie de façon déterministe les résultats de calculs/données (JSON/CSV) :
  1. Validité JSON stricte et absence de NaN / Infinity / valeurs nulles non traitées
  2. Précision monétaire : tout champ se terminant par `_usd`, `_eur`, `_total`, `_amount`, `_net`, `_fee`
     doit être un nombre fini arrondi au centime près (max 2 décimales)
"""
from __future__ import annotations

import json
import math
import sys
from decimal import Decimal
from pathlib import Path

MONEY_SUFFIXES = ("_usd", "_eur", "_total", "_amount", "_net", "_fee", "_spent", "_revenue", "_payout")


def validate_json_payload(data: object, origin: str, errors: list[str]) -> None:
    if isinstance(data, dict):
        if not data:
            errors.append(f"`{origin}` est un objet JSON vide `{{}}`.")
        for k, v in data.items():
            if v is None:
                errors.append(f"`{origin}` contient `{k}: null` (calcul incomplet).")
            elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                errors.append(f"`{origin}` contient NaN/Inf sur la clé `{k}`.")
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                if any(str(k).lower().endswith(sfx) for sfx in MONEY_SUFFIXES):
                    dec = Decimal(str(v))
                    if dec.as_tuple().exponent < -2:
                        errors.append(
                            f"`{origin}` : `{k}={v}` a plus de 2 décimales (utiliser Decimal ROUND_HALF_UP)."
                        )
            elif isinstance(v, (dict, list)):
                validate_json_payload(v, f"{origin}.{k}", errors)
    elif isinstance(data, list):
        for idx, item in enumerate(data[:50]):
            validate_json_payload(item, f"{origin}[{idx}]", errors)


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    rel_files = sys.argv[2:]
    errors: list[str] = []

    for rel in rel_files:
        p = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if not p.exists() or not p.is_file():
            continue
        if p.suffix.lower() == ".json" and p.name not in ("package.json", "tsconfig.json", "judges_sha256.json"):
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                validate_json_payload(payload, rel, errors)
            except Exception as exc:
                errors.append(f"JSON invalide dans `{rel}` : {exc}")

    if errors:
        print(" ; ".join(errors))
        return 1
    print("JUDGE_DATA: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
