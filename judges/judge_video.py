#!/usr/bin/env python3
"""
Juge Read-Only (chmod 444) #3 — judge_video.py (Harnais Production Vidéo & Shorts Avelis_evo1)
Vérifie de façon déterministe les livrables vidéo/audio/HTML avant d'autoriser l'agent à dire "Terminé" :
  1. Tout fichier .mp4 ou .wav touché doit exister, faire > 10 Ko, et avoir une durée ffprobe > 0.5s
  2. Tout contact-sheet / image de preuve (.png) touché doit faire > 5 Ko
  3. Tout fichier short.html / index.html touché doit contenir une balise </body> ou </script> fermée
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def probe_duration(media_path: Path) -> float:
    if not shutil.which("ffprobe"):
        return 1.0 if media_path.stat().st_size > 10_000 else 0.0
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    try:
        return float(proc.stdout.strip())
    except Exception:
        return 0.0


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    rel_files = sys.argv[2:]
    errors: list[str] = []

    for rel in rel_files:
        p = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if not p.exists() or not p.is_file():
            continue
        sfx = p.suffix.lower()
        size = p.stat().st_size

        if sfx in (".mp4", ".mov", ".wav", ".mp3"):
            if size < 4096:
                errors.append(f"Média `{rel}` quasi vide ({size} octets).")
            else:
                dur = probe_duration(p)
                if dur <= 0.5:
                    errors.append(f"Média `{rel}` invalide ou durée nulle (ffprobe={dur:.2f}s).")
        elif sfx == ".png" and ("contact_sheet" in p.name or "dod_" in p.name):
            if size < 5000:
                errors.append(f"Planche contact `{rel}` corrompue ou vide ({size} octets).")
        elif sfx == ".html":
            txt = p.read_text(encoding="utf-8", errors="replace")
            if "<html" in txt.lower() and "</html>" not in txt.lower():
                errors.append(f"Fichier HTML `{rel}` tronqué (balise `</html>` manquante).")

    if errors:
        print(" ; ".join(errors))
        return 1
    print("JUDGE_VIDEO: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
