#!/usr/bin/env python3
"""
Juge Read-Only (chmod 444) #5 — judge_po.py (Product Owner / Product Manager TI)
Vérifie de façon déterministe une User Story ou un Backlog (.md / .json) avant d'autoriser l'arrêt :
  1. Structure INVEST obligatoire : "En tant que <persona précis>" / "Je veux" / "Afin de" (ou As a / I want / So that)
     et interdiction du persona générique "utilisateur" non qualifié
  2. Présence explicite des 3 cas limites obligatoires : État vide (Empty state), Erreur réseau/API, Permissions/Rôles
  3. Critères d'acceptation en Gherkin (Given/When/Then ou Soit/Quand/Alors)
  4. Si JSON de backlog avec dépendances `blocked_by`, vérifie l'absence de cycle (DAG valide) et de score R.I.C.E. nul
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def validate_po_markdown(fpath: Path, rel: str) -> list[str]:
    text = fpath.read_text(encoding="utf-8", errors="replace")
    low = text.lower()
    errors: list[str] = []

    has_fr = all(k in low for k in ("en tant que ", "je veux ", "afin de "))
    has_en = all(k in low for k in ("as a ", "i want ", "so that "))
    if not (has_fr or has_en):
        errors.append(f"[PO `{rel}`] Structure INVEST manquante (`En tant que ... / Je veux ... / Afin de ...`).")

    if re.search(r"en tant qu['e]\s*utilisateur\s*[,\n]", low):
        errors.append(f"[PO `{rel}`] Persona trop vague (`En tant qu'utilisateur`) : nomme le rôle métier exact.")

    edge_checks = [
        (("état vide", "empty state", "aucun résultat"), "État vide (Empty state)"),
        (("erreur", "timeout", "indisponible", "500", "400"), "Cas d'erreur API/Réseau"),
        (("permission", "rôle", "accès", "autorisé", "403", "rbac"), "Permissions & Rôles"),
    ]
    for keywords, label in edge_checks:
        if not any(kw in low for kw in keywords):
            errors.append(f"[PO `{rel}`] Cas limite PO manquant : `{label}`.")

    has_gherkin = all(k in low for k in ("given ", "when ", "then ")) or all(k in low for k in ("soit ", "quand ", "alors "))
    if not has_gherkin:
        errors.append(f"[PO `{rel}`] Scénarios Gherkin (`Given/When/Then` ou `Soit/Quand/Alors`) manquants.")

    return errors


def validate_po_backlog_json(fpath: Path, rel: str) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"[PO `{rel}`] JSON invalide : {exc}"]

    stories = data.get("stories", data) if isinstance(data, dict) else data
    if not isinstance(stories, list) or not stories:
        return [f"[PO `{rel}`] Liste de stories vide ou absente."]

    graph: dict[str, list[str]] = {}
    for st in stories:
        if not isinstance(st, dict):
            continue
        sid = str(st.get("id", ""))
        deps = [str(d) for d in (st.get("blocked_by") or [])]
        graph[sid] = deps
        if "rice_score" in st and (st["rice_score"] is None or float(st["rice_score"]) <= 0):
            errors.append(f"[PO `{rel}`] Story `{sid}` a un `rice_score` nul ou négatif.")

    # Détection de cycle dans blocked_by
    visited: dict[str, int] = {}

    def has_cycle(node: str) -> bool:
        state = visited.get(node, 0)
        if state == 1:
            return True
        if state == 2:
            return False
        visited[node] = 1
        for nxt in graph.get(node, []):
            if nxt in graph and has_cycle(nxt):
                return True
        visited[node] = 2
        return False

    for sid in graph:
        if has_cycle(sid):
            errors.append(f"[PO `{rel}`] Cycle de dépendances (`blocked_by`) détecté impliquant `{sid}`.")
            break

    return errors


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    rel_files = sys.argv[2:]
    errors: list[str] = []

    for rel in rel_files:
        p = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if not p.exists() or not p.is_file():
            continue
        if p.suffix.lower() == ".md":
            errors.extend(validate_po_markdown(p, rel))
        elif p.suffix.lower() == ".json":
            errors.extend(validate_po_backlog_json(p, rel))

    if errors:
        print(" ; ".join(errors))
        return 1
    print("JUDGE_PO: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
