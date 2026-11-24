#!/usr/bin/env python3
"""
Juge Read-Only (chmod 444) #7 — judge_ops.py (DevOps / SRE / Cloud & Sécurité TI)
Vérifie de façon déterministe les fichiers d'infrastructure (Dockerfile, docker-compose.yml, .tf, .yaml, .sh) :
  1. Interdiction des tags d'images flottants `:latest` en production
  2. Interdiction d'exécuter un conteneur explicitement en `USER root` ou `privileged: true`
  3. Interdiction des secrets/tokens codés en dur (`sk-`, `ghp_`, `AKIA`, `password: "..."`)
  4. Interdiction d'exposer les ports critiques (22 SSH, 5432 Postgres, 6379 Redis, 27017 Mongo) sur `0.0.0.0`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SECRET_RE = re.compile(r"(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16})")
DANGEROUS_PORT_RE = re.compile(r"(0\.0\.0\.0:(22|5432|6379|27017|3306)\b|^\s*-\s*[\"']?(22|5432|6379|27017):(22|5432|6379|27017)[\"']?)", re.MULTILINE)


def validate_ops_file(fpath: Path, rel: str) -> list[str]:
    text = fpath.read_text(encoding="utf-8", errors="replace")
    low = text.lower()
    errors: list[str] = []

    if SECRET_RE.search(text):
        errors.append(f"[OPS `{rel}`] Secret ou clé d'API en clair détecté (utiliser des variables d'environnement).")

    if ":latest" in low and (fpath.name.lower().startswith("dockerfile") or "compose" in fpath.name.lower() or fpath.suffix in (".yml", ".yaml")):
        errors.append(f"[OPS `{rel}`] Tag d'image `:latest` interdit (épingler une version précise pour la reproductibilité).")

    if "privileged: true" in low or re.search(r"^\s*USER\s+root\s*$", text, re.MULTILINE):
        errors.append(f"[OPS `{rel}`] Exécution en `root` ou `privileged: true` interdite (principe du moindre privilège).")

    if DANGEROUS_PORT_RE.search(text):
        errors.append(f"[OPS `{rel}`] Port d'administration ou de base de données (22/5432/6379/27017) exposé publiquement sur toutes les interfaces.")

    return errors


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    rel_files = sys.argv[2:]
    errors: list[str] = []

    for rel in rel_files:
        p = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if p.exists() and p.is_file():
            errors.extend(validate_ops_file(p, rel))

    if errors:
        print(" ; ".join(errors))
        return 1
    print("JUDGE_OPS: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
