#!/usr/bin/env python3
"""
lock_judges.py — Scelle les Juges en lecture seule (chmod 444) et génère leur manifeste SHA-256.
Garantit l'invariant de sécurité Mode 5 de Google arXiv:2611.22299 Table III.A.1.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

JUDGES_DIR = Path(__file__).resolve().parent


def lock_all_judges() -> dict[str, str]:
    manifest: dict[str, str] = {}
    manifest_path = JUDGES_DIR / "judges_sha256.json"
    if manifest_path.exists():
        os.chmod(manifest_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

    for jfile in sorted(JUDGES_DIR.glob("judge_*.py")):
        digest = hashlib.sha256(jfile.read_bytes()).hexdigest()
        manifest[jfile.name] = digest
        # Verrouillage matériel en lecture seule : chmod 444 (r--r--r--)
        os.chmod(jfile, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.chmod(manifest_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return manifest


if __name__ == "__main__":
    m = lock_all_judges()
    for name, sha in m.items():
        print(f"🔒 {name} verrouillé en chmod 444 | SHA-256: {sha[:16]}...")
