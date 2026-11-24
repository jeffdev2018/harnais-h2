#!/usr/bin/env python3
"""
Juge Read-Only (chmod 444) #4 — judge_af.py (Analyste Fonctionnel / Business Analyst TI)
Vérifie de façon déterministe une spécification fonctionnelle (.md) avant d'autoriser l'arrêt :
  1. Présence des sections obligatoires (Acteurs, Règles de Gestion, Critères d'Acceptation Gherkin, Cas d'Erreur)
  2. Traçabilité 1:1 : chaque Règle de Gestion numérotée (RG-01, RG-02...) DOIT être citée dans les tests Gherkin
  3. Syntaxe Gherkin valide (Given/When/Then ou Soit/Quand/Alors)
  4. Absence de termes flous interdits ("TBD", "à définir", "etc.", "à préciser", "intuitif", "rapide")
  5. Fermeture propre des diagrammes Mermaid éventuels
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    "## Acteurs",
    "## Règles de Gestion",
    "## Critères d'Acceptation",
    "## Cas d'Erreur",
]
FORBIDDEN_VAGUE = ("tbd", "à définir", "etc.", "à préciser", "todo", "intuitif", "rapide")


def validate_af_spec(fpath: Path, rel: str) -> list[str]:
    text = fpath.read_text(encoding="utf-8", errors="replace")
    low = text.lower()
    errors: list[str] = []

    for sec in REQUIRED_SECTIONS:
        if sec.lower() not in low:
            errors.append(f"[AF `{rel}`] Section obligatoire manquante : `{sec}`")

    rgs = sorted(set(re.findall(r"\bRG-\d{2,3}\b", text)))
    if not rgs:
        errors.append(f"[AF `{rel}`] Aucune règle de gestion numérotée (`RG-01`, `RG-02`...) définie.")

    gherkin_idx = low.find("## critères d'acceptation")
    gherkin_part = low[gherkin_idx:] if gherkin_idx != -1 else ""
    for rg in rgs:
        if rg.lower() not in gherkin_part:
            errors.append(f"[AF `{rel}`] Traçabilité rompue : `{rg}` n'est couverte par aucun scénario Gherkin.")

    has_en_gherkin = all(k in gherkin_part for k in ("given ", "when ", "then "))
    has_fr_gherkin = all(k in gherkin_part for k in ("soit ", "quand ", "alors "))
    if not (has_en_gherkin or has_fr_gherkin):
        errors.append(f"[AF `{rel}`] Critères d'acceptation non conformes à Gherkin (`Given/When/Then` ou `Soit/Quand/Alors`).")

    for word in FORBIDDEN_VAGUE:
        if re.search(rf"\b{re.escape(word)}\b", low):
            errors.append(f"[AF `{rel}`] Terme flou interdit dans une spec TI : `{word}`.")

    if "```mermaid" in low and low.count("```") % 2 != 0:
        errors.append(f"[AF `{rel}`] Bloc diagramme `mermaid` non refermé.")

    return errors


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    rel_files = sys.argv[2:]
    errors: list[str] = []

    for rel in rel_files:
        p = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if p.exists() and p.is_file() and p.suffix.lower() == ".md":
            errors.extend(validate_af_spec(p, rel))

    if errors:
        print(" ; ".join(errors))
        return 1
    print("JUDGE_AF: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
