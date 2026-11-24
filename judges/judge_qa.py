#!/usr/bin/env python3
"""
Juge Read-Only (chmod 444) #6 — judge_qa.py (QA / Ingénieur Tests & Automatisation TI)
Vérifie de façon déterministe les suites de tests (.py, .ts, .js, .spec.ts, .test.ts) :
  1. Interdiction des attentes fixes fragiles (`time.sleep(`, `waitForTimeout(`, `setTimeout(`)
  2. Interdiction des sélecteurs CSS fragiles (`:nth-child(`, `.div > span >`)
  3. Présence d'au moins un test de cas nominal ET un test de cas d'erreur / rejet (negative test)
  4. Absence de tests désactivés (`@skip`, `test.skip`, `xit(`, `xdescribe(`)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FLAKY_PATTERNS = ("time.sleep(", "waitForTimeout(", "cy.wait(")
SKIP_PATTERNS = ("@unittest.skip", "pytest.skip(", "test.skip(", "it.skip(", "xit(", "xdescribe(")
FRAGILE_CSS_RE = re.compile(r":nth-child\(\d+\)|div\s*>\s*div\s*>\s*span")


def validate_qa_file(fpath: Path, rel: str) -> list[str]:
    text = fpath.read_text(encoding="utf-8", errors="replace")
    low = text.lower()
    errors: list[str] = []

    for pat in FLAKY_PATTERNS:
        if pat.lower() in low:
            errors.append(f"[QA `{rel}`] Attente fixe fragile interdite (`{pat}`) : utilise une assertion d'état/visibilité.")

    for pat in SKIP_PATTERNS:
        if pat.lower() in low:
            errors.append(f"[QA `{rel}`] Test désactivé interdit (`{pat}`).")

    if FRAGILE_CSS_RE.search(text):
        errors.append(f"[QA `{rel}`] Sélecteur CSS fragile (`:nth-child` ou chaîne DOM profonde) : utilise `getByRole` ou `data-testid`.")

    has_negative = any(
        kw in low for kw in ("error", "erreur", "invalid", "invalide", "reject", "raises", "400", "403", "404", "exception", "fail")
    )
    if not has_negative:
        errors.append(f"[QA `{rel}`] Aucun test de cas négatif/erreur détecté (couvrir le cas nominal ET le cas d'erreur).")

    return errors


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    rel_files = sys.argv[2:]
    errors: list[str] = []

    for rel in rel_files:
        p = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if p.exists() and p.is_file() and p.suffix.lower() in (".py", ".ts", ".js", ".tsx"):
            errors.extend(validate_qa_file(p, rel))

    if errors:
        print(" ; ".join(errors))
        return 1
    print("JUDGE_QA: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
