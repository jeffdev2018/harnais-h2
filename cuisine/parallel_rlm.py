#!/usr/bin/env python3
"""
Brique v4.5 — parallel_rlm.py (Map-Reduce en Mode Cuisine inspiré de `rlm()` dans Prime Agent arXiv:2608.23552 §2.3)
Exécute une opération Mode Cuisine (peek, query Python L2, ou verify Juge chmod 444) en parallèle
sur N fichiers dans des workers isolés, et ne renvoie en contexte L1 que le tableau récapitulatif consolidé.

Usages :
  1. Aperçu schéma parallèle sur N fichiers :
     h2 parallel peek <f1.csv> <f2.csv> ...
  2. Requête Python L2 Map-Reduce sur N fichiers (ex: total par fichier + grand total) :
     h2 parallel query "<expr_python>" <f1.csv> <f2.csv> ...
  3. Vérification parallèle de N fichiers par un Juge Métier TI (chmod 444) :
     h2 parallel verify <auto|code|data|video|af|po|qa|ops> <f1> <f2> ...
"""
from __future__ import annotations

import concurrent.futures
import csv
import datetime
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

HARNESS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS_ROOT / "core"))

from context_mgr import build_data_schema_preview  # noqa: E402
from verify import run_pre_stop_verifier  # noqa: E402


def d2(val: object) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _eval_one_file(target: Path, expr: str) -> tuple[str, Any]:
    if not target.exists():
        return target.name, {"error": f"Fichier introuvable : {target}"}

    sfx = target.suffix.lower()
    rows: list[Any] = []
    data: Any = None
    if sfx in (".csv", ".tsv"):
        delim = "\t" if sfx == ".tsv" else ","
        with target.open("r", encoding="utf-8", errors="replace") as f:
            rows = list(csv.DictReader(f, delimiter=delim))
        data = rows
    elif sfx == ".json":
        data = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(data, list):
            rows = data
    elif sfx == ".jsonl":
        rows = [json.loads(ln) for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()]
        data = rows
    else:
        data = target.read_text(encoding="utf-8", errors="replace").splitlines()
        rows = data

    env = {
        "data": data,
        "rows": rows,
        "file_name": target.name,
        "Decimal": Decimal,
        "d2": d2,
        "datetime": datetime,
        "json": json,
        "sum": sum,
        "len": len,
        "min": min,
        "max": max,
        "sorted": sorted,
        "round": round,
        "float": float,
        "int": int,
        "str": str,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "bool": bool,
        "abs": abs,
        "any": any,
        "all": all,
    }
    try:
        res = eval(expr, env)  # noqa: S307
        if isinstance(res, Decimal):
            res = float(d2(res))
        return target.name, res
    except Exception as exc:
        return target.name, {"error": str(exc)}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    sub = sys.argv[1].lower()
    if sub == "peek":
        files = [Path(p).resolve() for p in sys.argv[2:]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            previews = list(ex.map(lambda p: build_data_schema_preview(p, sample_rows=1), files))
        print(f"[H2 PARALLEL PEEK — {len(files)} fichier(s) en Mode Cuisine L1]\n\n" + "\n\n".join(previews))
        return 0

    if sub == "query":
        if len(sys.argv) < 4:
            sys.exit('Usage: h2 parallel query "<expr_python>" <f1> <f2> ...')
        expr = sys.argv[2]
        files = [Path(p).resolve() for p in sys.argv[3:]]
        results: dict[str, Any] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(_eval_one_file, p, expr) for p in files]
            for f in futs:
                fname, val = f.result()
                results[fname] = val

        # Calcul automatique d'une réduction (Reduce) si toutes les valeurs sont numériques
        numeric_vals = [Decimal(str(v)) for v in results.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        payload: dict[str, Any] = {"files_processed": len(files), "map_results": results}
        if numeric_vals and len(numeric_vals) == len(files):
            payload["reduce_sum"] = float(d2(sum(numeric_vals, Decimal("0.00"))))
        print("[H2 PARALLEL RLM MAP-REDUCE L2->L1]\n" + json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if sub == "verify":
        if len(sys.argv) < 4:
            sys.exit("Usage: h2 parallel verify <auto|code|data|video|af|po|qa|ops> <f1> <f2> ...")
        domain = sys.argv[2]
        files = [str(Path(p).resolve()) for p in sys.argv[3:]]
        ok, errs = run_pre_stop_verifier(Path.cwd(), edited_files=files, domain=domain)
        if ok:
            print(f"[H2 PARALLEL VERIFY OK] {len(files)} fichier(s) certifiés par le Juge `{domain}` (chmod 444) + Reçu SHA-256 signé.")
            return 0
        print("[H2 PARALLEL VERIFY ÉCHEC]\n- " + "\n- ".join(errs))
        return 1

    sys.exit(f"Sous-commande parallel inconnue : {sub}")


if __name__ == "__main__":
    sys.exit(main())
