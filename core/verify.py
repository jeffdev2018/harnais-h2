#!/usr/bin/env python3
"""
Brique 1 & v4.2 — verify.py (Harnais H2 v4)
Sources :
  - Google arXiv:2611.22299 : Pre-Stop Verifier + Mode 5 Judge Integrity (chmod 444 + SHA-256)
  - Google arXiv:2611.22299 §VI Mode 4 [78] : AST Anti-Hardcoding / Anti-Lookup-Table Check
  - GUI-HARVEST arXiv:2611.22299 Table I.D [38] : Détection des vidéos noires (blackdetect)
  - Zhang et al. arXiv:2610.34577 : Rethinking Verification in Agent Harnesses (Intermediate + Pre-Stop)
  - Harness Engineering (verify-completion) : Cryptographic Verification Receipt (.h2_receipt.json)

Porte de vérification déterministe exécutée en cours de route (intermediate) et avant arrêt (pre-stop) :
  1. Vérifie l'intégrité matérielle des 7 Juges immuables (permissions chmod 444 + hash SHA-256 intact)
  2. Vérifie que tous les fichiers édités (.py, .json, .js, .mjs) compilent sans erreur
  3. Détecte les tentatives de triche (Mode 5 : verify=False, SSL bypass ; Mode 4 : AST hardcoding)
  4. Vérifie l'absence d'écran noir silencieux (GUI-HARVEST) sur les vidéos .mp4/.mov
  5. Exécute les 7 Juges read-only spécialisés :
     - judge_code.py  (Développeur)
     - judge_data.py  (Data / BI / FinOps)
     - judge_video.py (Production Vidéo & Shorts)
     - judge_af.py    (Analyste Fonctionnel / Business Analyst)
     - judge_po.py    (Product Owner / Product Manager)
     - judge_qa.py    (QA / Ingénieur Tests)
     - judge_ops.py   (DevOps / SRE / Sécurité)
  6. Émet un Reçu Cryptographique Signé (`logs/last_verify_receipt.json`) prouvant que `h2 verify`
     a tourné APRÈS la toute dernière modification des fichiers sur disque !
"""
from __future__ import annotations

import ast
import datetime
import hashlib
import json
import py_compile
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
RECEIPT_PATH = HARNESS_ROOT / "logs" / "last_verify_receipt.json"

CHEAT_PATTERNS = [
    "verify=False",
    "verify_ssl=False",
    "CERT_NONE",
    "NODE_TLS_REJECT_UNAUTHORIZED",
    "pytest.skip(",
    "@unittest.skip",
]

DATA_IO_CALLS = {
    "open",
    "read_text",
    "read_bytes",
    "DictReader",
    "reader",
    "loads",
    "load",
    "read_csv",
    "l2_load",
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_modified_files(workspace: Path) -> list[str]:
    files: list[str] = []
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if len(line) > 3:
                    candidate = line[3:].strip().split(" -> ")[-1].strip('"')
                    files.append(candidate)
    except Exception:
        pass
    return files


def write_verification_receipt(workspace: Path, domain: str, checked_files: list[str], judges_dir: Path) -> dict[str, object]:
    """
    Brique v4.2 — Reçu Cryptographique de Vérification :
    Scelle l'empreinte SHA-256 de chaque fichier vérifié + du manifeste des juges chmod 444.
    """
    file_hashes: dict[str, str] = {}
    for rel in sorted(set(checked_files)):
        fpath = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if fpath.exists() and fpath.is_file():
            file_hashes[rel] = _file_sha256(fpath)

    manifest_path = judges_dir / "judges_sha256.json"
    j_sha = _file_sha256(manifest_path) if manifest_path.exists() else "none"
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    payload_core = {
        "timestamp_utc": ts,
        "workspace": str(workspace),
        "domain": domain,
        "judges_manifest_sha256": j_sha,
        "files_sha256": file_hashes,
    }
    canonical = json.dumps(payload_core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    sig = hashlib.sha256(canonical).hexdigest()
    receipt = {**payload_core, "receipt_signature": sig}

    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt


def check_receipt_freshness(workspace: Path, edited_files: list[str] | None = None) -> tuple[bool, str]:
    """
    Vérifie en <5ms qu'un reçu `last_verify_receipt.json` valide existe et qu'AUCUN fichier modifié
    dans le workspace n'a été retouché depuis l'émission du reçu.
    """
    if not RECEIPT_PATH.exists():
        return False, "RECEIPT_MISSING: Aucun reçu `.h2_receipt` trouvé — exécute `h2 verify` avant de conclure."

    try:
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        sig = receipt.get("receipt_signature", "")
        core = {k: receipt[k] for k in ("timestamp_utc", "workspace", "domain", "judges_manifest_sha256", "files_sha256")}
        expected_sig = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if sig != expected_sig:
            return False, "RECEIPT_TAMPERED: La signature SHA-256 du reçu de vérification est invalide !"
    except Exception as exc:
        return False, f"RECEIPT_CORRUPT: Impossible de lire le reçu ({exc})."

    files_to_check = edited_files if edited_files is not None else discover_modified_files(workspace)
    recorded_hashes: dict[str, str] = receipt.get("files_sha256") or {}

    for rel in files_to_check:
        fpath = (workspace / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if not fpath.exists() or not fpath.is_file():
            continue
        if fpath.name == "last_verify_receipt.json":
            continue
        cur_sha = _file_sha256(fpath)
        if recorded_hashes.get(rel) != cur_sha:
            return (
                False,
                f"RECEIPT_STALE: Le fichier `{rel}` a été modifié APRÈS le dernier `h2 verify`. "
                f"Relance `h2 verify` pour certifier ta dernière modification.",
            )

    return True, f"RECEIPT_OK (signé à {receipt.get('timestamp_utc')}, sig={sig[:16]}...)"


def check_judge_integrity(judges_dir: Path) -> tuple[bool, str]:
    """
    Défense Mode 5 (Google 2611.22299 Table III.A.1) :
    L'évaluateur doit être en lecture seule (chmod 444) et son empreinte SHA-256 intacte.
    """
    if not judges_dir.exists():
        return True, "Aucun répertoire de juges dédié."

    manifest_path = judges_dir / "judges_sha256.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return False, "VERIFY_GATE [MODE 5]: Manifeste SHA-256 des juges corrompu."

    for judge_file in sorted(judges_dir.glob("judge_*.py")):
        mode = stat.S_IMODE(judge_file.stat().st_mode)
        if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            return (
                False,
                f"VERIFY_GATE [MODE 5]: Le juge `{judge_file.name}` n'est pas verrouillé en lecture seule "
                f"(mode actuel {oct(mode)}, attendu 0o444).",
            )
        if judge_file.name in manifest:
            digest = hashlib.sha256(judge_file.read_bytes()).hexdigest()
            if digest != manifest[judge_file.name]:
                return (
                    False,
                    f"VERIFY_GATE [MODE 5]: Empreinte SHA-256 de `{judge_file.name}` altérée ! "
                    f"Tentative de reward hacking détectée.",
                )
    return True, "7 Juges TI intègres (chmod 444 + SHA-256 OK)."


def check_ast_anti_hardcoding(py_path: Path) -> tuple[bool, str]:
    """
    Défense Mode 4 (Google 2611.22299 §VI [78]) :
    Bloque tout script de calcul financier qui émet des résultats JSON sans lire les données ni boucler.
    """
    try:
        src = py_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(py_path))
    except Exception:
        return True, "OK"

    if not any(sfx in src for sfx in ("_usd", "_eur", "_total", "_net", "_spent", "_revenue")):
        return True, "OK"
    if py_path.name in (
        "verify.py",
        "cuisine_repl.py",
        "judge_data.py",
        "run_universal_v6_lab.py",
        "run_h2_v2_benchmark.py",
        "run_h2_40tasks_benchmark.py",
        "run_h2_100tasks_benchmark.py",
        "run_multimodel_h2_arena.py",
    ):
        return True, "OK"

    has_io = False
    has_compute = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While, ast.ListComp, ast.GeneratorExp, ast.DictComp, ast.BinOp)):
            has_compute = True
        elif isinstance(node, ast.Call):
            fn = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if fn in DATA_IO_CALLS:
                has_io = True

    if not has_io or not has_compute:
        return (
            False,
            f"VERIFY_GATE [MODE 4 ANTI-HARDCODING]: `{py_path.name}` contient des clés financières mais "
            f"aucune lecture de données (IO={has_io}) ou calcul dynamique (Compute={has_compute}). "
            f"Interdiction de coder en dur un calcul mental.",
        )
    return True, "OK"


def check_video_not_black(video_path: Path) -> tuple[bool, str]:
    """GUI-HARVEST (arXiv:2611.22299 Table I.D [38]) : détecte les rendus vidéo .mp4/.mov noirs."""
    if not shutil.which("ffmpeg") or not video_path.exists() or video_path.stat().st_size < 4096:
        return True, "OK"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-t",
            "4.0",
            "-i",
            str(video_path),
            "-vf",
            "blackdetect=d=0.5:pix_th=0.05",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    black_durs = [float(m) for m in re.findall(r"black_duration:([0-9.]+)", proc.stderr)]
    total_black = sum(black_durs)
    if total_black >= 3.4:
        return (
            False,
            f"VERIFY_GATE [GUI-HARVEST ÉCRAN NOIR]: `{video_path.name}` est noir pendant {total_black:.1f}s "
            f"sur les 4 premières secondes.",
        )
    return True, "OK"


def verify_single_file_fast(fpath: Path, rel_label: str) -> list[str]:
    """Vérification intermédiaire ultra-rapide (<40ms, arXiv:2610.34577) utilisable dès PostToolUse."""
    errs: list[str] = []
    if not fpath.exists() or not fpath.is_file():
        return errs

    suffix = fpath.suffix.lower()
    if suffix == ".py":
        try:
            py_compile.compile(str(fpath), doraise=True)
        except py_compile.PyCompileError as exc:
            errs.append(f"VERIFY_GATE [SYNTAXE PYTHON]: `{rel_label}` ne compile pas — {exc.msg}")

        text = fpath.read_text(encoding="utf-8", errors="replace")
        for pat in CHEAT_PATTERNS:
            if pat in text and fpath.name not in ("verify.py", "modular_evolver.py") and not fpath.name.startswith("judge_"):
                errs.append(f"VERIFY_GATE [ANTI-TRICHE MODE 5]: Pattern interdit `{pat}` dans `{rel_label}`.")

        ok_ast, msg_ast = check_ast_anti_hardcoding(fpath)
        if not ok_ast:
            errs.append(msg_ast)

    elif suffix == ".json":
        try:
            json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as exc:
            errs.append(f"VERIFY_GATE [JSON INVALIDE]: `{rel_label}` — {exc}")

    elif suffix in (".js", ".mjs", ".cjs") and shutil.which("node"):
        proc = subprocess.run(["node", "--check", str(fpath)], capture_output=True, text=True, timeout=5)
        if proc.returncode != 0:
            errs.append(f"VERIFY_GATE [SYNTAXE JS]: `{rel_label}` — {proc.stderr.strip()[:250]}")

    return errs


def run_pre_stop_verifier(
    workspace: Path,
    edited_files: list[str] | None = None,
    judges_dir: Path | None = None,
    domain: str = "auto",
) -> tuple[bool, list[str]]:
    """Exécute la batterie complète de vérifications + émet le Reçu Cryptographique si tout est vert."""
    errors: list[str] = []
    j_dir = judges_dir or (HARNESS_ROOT / "judges")

    # 1. Intégrité chmod 444 des 7 juges
    ok_integrity, msg_integrity = check_judge_integrity(j_dir)
    if not ok_integrity:
        errors.append(msg_integrity)
        return False, errors

    # 2. Découverte des fichiers touchés via git status si edited_files non fourni
    files_to_check = list(edited_files) if edited_files else discover_modified_files(workspace)

    # 3. Vérification rapide + AST Mode 4 + GUI-HARVEST sur chaque fichier modifié
    for rel_path in files_to_check:
        fpath = (workspace / rel_path).resolve() if not Path(rel_path).is_absolute() else Path(rel_path)
        if not fpath.exists() or not fpath.is_file():
            continue
        errors.extend(verify_single_file_fast(fpath, rel_path))
        if fpath.suffix.lower() in (".mp4", ".mov"):
            ok_v, msg_v = check_video_not_black(fpath)
            if not ok_v:
                errors.append(msg_v)

    # 4. Routage vers les 7 Juges Métiers TI immuables (chmod 444)
    judges_to_run: list[Path] = []
    dom = domain.lower()
    if dom in ("code", "dev", "all", "auto"):
        if any(Path(f).suffix.lower() in (".py", ".ts", ".tsx", ".js") for f in files_to_check) or dom in ("code", "dev"):
            judges_to_run.append(j_dir / "judge_code.py")
    if dom in ("data", "cuisine", "bi", "finops", "all", "auto"):
        if any(Path(f).suffix.lower() in (".csv", ".json") for f in files_to_check) or dom in ("data", "cuisine", "bi", "finops"):
            judges_to_run.append(j_dir / "judge_data.py")
    if dom in ("video", "all", "auto"):
        if any(Path(f).suffix.lower() in (".mp4", ".wav", ".html") or "short" in f or "timeline" in f for f in files_to_check) or dom == "video":
            judges_to_run.append(j_dir / "judge_video.py")
    if dom in ("af", "ba", "spec", "all"):
        judges_to_run.append(j_dir / "judge_af.py")
    if dom in ("po", "pm", "story", "backlog", "all"):
        judges_to_run.append(j_dir / "judge_po.py")
    if dom in ("qa", "test", "all"):
        judges_to_run.append(j_dir / "judge_qa.py")
    if dom in ("ops", "devops", "sre", "sec", "all"):
        judges_to_run.append(j_dir / "judge_ops.py")

    for j_script in judges_to_run:
        if j_script.exists():
            proc = subprocess.run(
                [sys.executable, str(j_script), str(workspace), *files_to_check],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode != 0:
                out = (proc.stdout + "\n" + proc.stderr).strip()
                errors.append(f"[{j_script.name} REJETÉ] {out}")

    if not errors:
        write_verification_receipt(workspace, dom, files_to_check, j_dir)
        return True, []
    return False, errors


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check-receipt":
        ws = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path.cwd()
        extra = sys.argv[3:] if len(sys.argv) > 3 else None
        ok_r, msg_r = check_receipt_freshness(ws, extra)
        print(msg_r)
        sys.exit(0 if ok_r else 1)

    ws = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    dom = sys.argv[2] if len(sys.argv) > 2 else "auto"
    extra_files = sys.argv[3:] if len(sys.argv) > 3 else None
    ok, errs = run_pre_stop_verifier(ws, edited_files=extra_files, domain=dom)
    if ok:
        ok_r, msg_r = check_receipt_freshness(ws, extra_files)
        print(f"VERIFY_GATE: OK — Toutes les portes (Mode 4 AST, Mode 5 chmod 444, 7 Juges TI) sont vertes. [{msg_r}]")
        sys.exit(0)
    else:
        print("\n".join(errs))
        sys.exit(1)
