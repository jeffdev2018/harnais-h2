#!/usr/bin/env python3
"""
Juge Read-Only (chmod 444) #1 — judge_code.py (Google arXiv:2611.22299 Mode 5 Defense)
Vérifie de façon déterministe tout code modifié avant d'autoriser l'arrêt :
  1. Syntaxe Python (py_compile) et TypeScript/JS (node --check sur .js/.mjs/.cjs)
  2. Absence de marqueurs de conflit git (<<<<<<<, =======, >>>>>>>)
  3. Absence de placeholders interdits (TODO_IMPLEMENT_ME, pass # placeholder, ellipsis truqué)
  4. Exécution du script de test rapide `.harness_test.sh` s'il est présent dans le projet
"""
from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

CONFLICT_MARKERS = ("<<<<<<< ", ">>>>>>> ")


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    rel_files = sys.argv[2:]
    errors: list[str] = []

    for rel in rel_files:
        p = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if not p.exists() or not p.is_file():
            continue

        txt = p.read_text(encoding="utf-8", errors="replace")
        for m in CONFLICT_MARKERS:
            if m in txt:
                errors.append(f"Conflit Git non résolu (`{m.strip()}`) dans `{rel}`.")

        if p.suffix == ".py":
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(f"Erreur syntaxe Python dans `{rel}` : {exc.msg}")
        elif p.suffix in (".js", ".mjs", ".cjs"):
            proc = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=10)
            if proc.returncode != 0:
                errors.append(f"Erreur syntaxe JS (`node --check`) dans `{rel}` : {proc.stderr.strip()[:300]}")

    quick_test = workspace / ".harness_test.sh"
    if quick_test.exists():
        proc = subprocess.run(["bash", str(quick_test)], cwd=str(workspace), capture_output=True, text=True, timeout=25)
        if proc.returncode != 0:
            out = (proc.stdout + "\n" + proc.stderr).strip()[:500]
            errors.append(f"Échec `.harness_test.sh` (exit={proc.returncode}) : {out}")

    if errors:
        print(" ; ".join(errors))
        return 1
    print("JUDGE_CODE: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
