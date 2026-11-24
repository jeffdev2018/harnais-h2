#!/usr/bin/env python3
"""
Brique 2 (v2) — cuisine_repl.py (Prime Agent RLM Harness arXiv:2608.23552 §2.2-2.3)
Implémente la hiérarchie mémoire L1 / L2 / L3 avec :
  - L1 (Table / Contexte LLM) : schéma `peek` (~120 tokens) + résumés compacts
  - L2 (Cuisine / REPL Persistant) : mémoire de variables persistante entre appels (`.h2_l2_state.json`)
    avec `save(key, val)`, `load(key)`, `vars_l2()` et **Agentic Garbage Collection** (`h2 gc`) !
  - L3 (Garde-manger / Disque) : fichiers bruts (.csv, words.json, transcript.json) et sorties JSON vérifiées

Commandes :
  1. Aperçu schéma L1 (~120 tokens) :
     h2 peek <fichier.csv|json>
  2. Requête Python L2 avec persistance inter-tours (`save('k', v)` / `load('k')`) :
     h2 query <fichier.csv|json> "<expr_python>"
  3. Inspecter ou purger la mémoire L2 (Agentic Garbage Collection arXiv:2608.23552 §2.2) :
     h2 gc [list|clear|drop <cle>]
  4. Exécution d'un script L2 + validation par Juge chmod 444 (Anti-Hardcoding AST Mode 4 inclus) :
     h2 run <script.py> [sortie.json] [cle1,cle2,...]
"""
from __future__ import annotations

import csv
import datetime
import json
import subprocess
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

HARNESS_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = HARNESS_ROOT / "core"
JUDGES_DIR = HARNESS_ROOT / "judges"
L2_STATE_PATH = HARNESS_ROOT / "logs" / "l2_repl_state.json"

sys.path.insert(0, str(CORE_DIR))
from context_mgr import build_data_schema_preview  # noqa: E402
from verify import check_ast_anti_hardcoding, check_judge_integrity  # noqa: E402


def d2(val: object) -> Decimal:
    """Arrondi financier exact au centime près (ROUND_HALF_UP)."""
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _read_l2_store() -> dict[str, Any]:
    if not L2_STATE_PATH.exists():
        return {}
    try:
        return json.loads(L2_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_l2_store(store: dict[str, Any]) -> None:
    L2_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    L2_STATE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def l2_save(key: str, val: Any) -> Any:
    """Sauvegarde une valeur intermédiaire en mémoire L2 (hors contexte LLM) pour les tours suivants."""
    store = _read_l2_store()
    if isinstance(val, Decimal):
        val = float(d2(val))
    store[str(key)] = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "value": val,
    }
    _write_l2_store(store)
    return val


def l2_load(key: str, default: Any = None) -> Any:
    """Charge une valeur précédemment sauvegardée en mémoire L2."""
    store = _read_l2_store()
    entry = store.get(str(key))
    return entry["value"] if isinstance(entry, dict) and "value" in entry else default


def cmd_gc(action: str = "list", key: str | None = None) -> int:
    """Agentic Garbage Collection (Prime Agent arXiv:2608.23552 Fig. 2) sur la mémoire L2."""
    store = _read_l2_store()
    if action == "clear":
        _write_l2_store({})
        print("[CUISINE L2 GC] Mémoire L2 intégralement purgée (0 variable retenue).")
        return 0
    if action == "drop" and key:
        removed = store.pop(key, None)
        _write_l2_store(store)
        print(f"[CUISINE L2 GC] Variable `{key}` supprimée ({'trouvée' if removed else 'absente'}).")
        return 0

    if not store:
        print("[CUISINE L2 GC] Mémoire L2 vide.")
        return 0
    summary = []
    for k, meta in store.items():
        v = meta.get("value") if isinstance(meta, dict) else meta
        v_str = json.dumps(v, ensure_ascii=False, default=str)
        summary.append(f"  • {k} ({len(v_str)} octets) : {v_str[:120]}")
    print("[CUISINE L2 GC — Variables retenues hors contexte L1]\n" + "\n".join(summary))
    return 0


def cmd_peek(target: Path) -> int:
    print(build_data_schema_preview(target))
    return 0


def cmd_query(target: Path, expr: str) -> int:
    """Charge le fichier en L2 (hors fenêtre LLM) + expose `save(k,v)` / `load(k)` persistants."""
    rows: list[Any] = []
    data: object = None
    if target.exists():
        sfx = target.suffix.lower()
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
    elif str(target.name) not in ("-", "l2", "state"):
        sys.exit(f"[CUISINE ERREUR] Fichier introuvable : {target}")

    l2_store = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in _read_l2_store().items()}

    env = {
        "data": data,
        "rows": rows,
        "l2": l2_store,
        "save": l2_save,
        "load": l2_load,
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
        "enumerate": enumerate,
        "zip": zip,
    }
    try:
        result = eval(expr, env)  # noqa: S307
    except Exception as exc:
        sys.exit(f"[CUISINE QUERY ERREUR] {exc}")

    if isinstance(result, Decimal):
        result = float(d2(result))
    out_str = json.dumps(result, ensure_ascii=False, default=str)
    if len(out_str) > 1200:
        out_str = out_str[:1200] + "... [résultat L2 tronqué pour protéger L1]"
    print(f"[CUISINE RLM L2->L1] {out_str}")
    return 0


def cmd_run(script_path: Path, out_json: Path | None, required_keys: list[str]) -> int:
    """Exécute un script Python en L2, sauvegarde le JSON en L3 et le soumet aux juges chmod 444."""
    ok_int, msg_int = check_judge_integrity(JUDGES_DIR)
    if not ok_int:
        sys.exit(msg_int)

    if not script_path.exists():
        sys.exit(f"[CUISINE RUN ERREUR] Script introuvable : {script_path}")

    ok_ast, msg_ast = check_ast_anti_hardcoding(script_path)
    if not ok_ast:
        sys.exit(f"[CUISINE RUN BLOQUÉ — MODE 4] {msg_ast}")

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        sys.exit(f"[CUISINE RUN ÉCHEC (exit={proc.returncode})]\n{proc.stderr.strip()[:600]}")

    lines = [ln.strip() for ln in proc.stdout.strip().splitlines() if ln.strip()]
    if not lines:
        sys.exit("[CUISINE RUN ÉCHEC] Le script n'a produit aucune sortie JSON.")

    last_line = lines[-1]
    try:
        payload = json.loads(last_line)
    except Exception as exc:
        sys.exit(f"[CUISINE RUN ÉCHEC] La dernière ligne n'est pas un JSON valide : {exc}\nSortie: {last_line[:300]}")

    missing = [k for k in required_keys if k not in payload]
    if missing:
        sys.exit(f"[CUISINE RUN ÉCHEC] Clés obligatoires manquantes dans le JSON : {missing}")

    target_json = out_json or script_path.with_suffix(".out.json")
    target_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Appel du juge read-only chmod 444 (inclut le détecteur AST Anti-Hardcoding Mode 4 sur script_path)
    judge_proc = subprocess.run(
        [
            sys.executable,
            str(JUDGES_DIR / "judge_data.py"),
            str(target_json.parent),
            str(target_json),
            str(script_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if judge_proc.returncode != 0:
        sys.exit(f"[JUGE DATA chmod 444 REJETÉ] {judge_proc.stdout.strip()}")

    print(
        f"[CUISINE RUN + JUGE 444 OK] Résultat sauvegardé dans `{target_json.name}` :\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    verb = sys.argv[1].lower()
    if verb == "gc":
        act = sys.argv[2].lower() if len(sys.argv) > 2 else "list"
        k = sys.argv[3] if len(sys.argv) > 3 else None
        return cmd_gc(act, k)
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    if verb == "peek":
        return cmd_peek(Path(sys.argv[2]).resolve())
    if verb == "query":
        if len(sys.argv) < 4:
            sys.exit('Usage: cuisine_repl.py query <fichier|l2> "<expr_python>"')
        t_arg = sys.argv[2]
        t_path = Path(t_arg) if t_arg in ("-", "l2", "state") else Path(t_arg).resolve()
        return cmd_query(t_path, sys.argv[3])
    if verb == "run":
        sc = Path(sys.argv[2]).resolve()
        out_p = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 and sys.argv[3] else None
        req = sys.argv[4].split(",") if len(sys.argv) > 4 and sys.argv[4] else []
        return cmd_run(sc, out_p, req)
    sys.exit(f"Commande inconnue : {verb}")


if __name__ == "__main__":
    sys.exit(main())
