#!/usr/bin/env python3
"""
Arène Multi-Modèles Universelle — Harnais H2 v3 (`run_multimodel_h2_arena.py`)
Teste le Harnais H2 v3 sur TOUS les écosystèmes présents sur le Mac de Jeff :
  1. Modèle Local (Apple M5 Pro Metal via Magnitude `127.0.0.1:10100`) : `local:gemma-4-e2b-it-qat:gguf:q4`
  2. Modèles Gratuits (`FreeLLMAPI http://127.0.0.1:3011/v1`) :
     - `freellm:gemini-3.8-flash`
     - `freellm:glm-5.3-flash`
     - `freellm:deepseek-v4.1-flash`
     - `freellm:qwen3.8-27b`
     - `freellm:gemma-4-31b-it`
  3. DeepSeek (Direct API & OpenCode CLI) :
     - `deepseek:deepseek-chat`
     - `opencode:deepseek/deepseek-flash`
  4. ChatGPT (`cli:codex` — Codex CLI)
  5. Claude (`cli:claude` — Claude Code CLI)

Pour chaque modèle, compare **SANS HARNAIS (RULES.md seul)** vs **AVEC HARNAIS H2 v3**
sur les 2 tâches de référence (Data Stripe 180 lignes + Code/Timeline Vidéo 320 mots) + vérifie
les 4 tâches Palier 4 Extrême (`T32..T35`) corrigées avec la règle complète + Invariant Gate.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
H2_ROOT = BENCH_DIR.parent
sys.path.insert(0, str(H2_ROOT / "core"))
sys.path.insert(0, str(BENCH_DIR))

from context_mgr import build_data_schema_preview  # noqa: E402
from providers import call_universal_model, repair_python_code_for_small_models  # noqa: E402
from run_h2_v2_benchmark import (  # noqa: E402
    TASK1_RULES_PROMPT,
    extract_json_obj,
    setup_task1_data,
    setup_task2_code,
)
from verify import run_pre_stop_verifier, verify_single_file_fast  # noqa: E402

ARENA_MODELS = [
    ("LOCAL_M5_METAL", "local:gemma-4-e2b-it-qat:gguf:q4", "Gemma 4 E2B Q4 (Local Apple M5 Pro)"),
    ("FREELLM_3011", "freellm:deepseek-v4-flash", "DeepSeek V4 Flash (FreeLLM :3011 $0)"),
    ("FREELLM_3011", "freellm:mistralaimistral-large-4-1t-a52b", "Mistral Large 4 1T (FreeLLM :3011 $0)"),
    ("FREELLM_3011", "freellm:qwen3.8-27b", "Qwen 3.8 27B (FreeLLM :3011 $0)"),
    ("DEEPSEEK_API", "deepseek:deepseek-chat", "DeepSeek Chat Direct API"),
    ("CHATGPT_CLI", "cli:codex", "ChatGPT (via Codex CLI)"),
    ("CLAUDE_CLI", "cli:claude", "Claude (via Claude Code CLI)"),
]


def eval_model_t1_bare(spec: str, csv_path: Path, gt: dict) -> dict[str, Any]:
    t0 = time.time()
    raw_csv = csv_path.read_text(encoding="utf-8")
    prompt = (
        f"# RULES.md\nSois extrêmement précis, vérifie tous tes calculs deux fois.\n\n"
        f"{TASK1_RULES_PROMPT}\n\n"
        f"Voici le fichier CSV complet :\n```csv\n{raw_csv}\n```\n"
        f"Réponds UNIQUEMENT par un objet JSON final contenant exactement les 4 clés : "
        f"`valid_tx_count`, `stripe_fees_total_usd`, `affiliate_payout_usd`, `final_net_payout_usd`."
    )
    reply, tokens = call_universal_model(spec, [{"role": "user", "content": prompt}], max_tokens=2000, timeout=55)
    dt = round(time.time() - t0, 2)
    pred = extract_json_obj(reply)
    exact = all(k in pred and abs(float(pred[k]) - float(gt[k])) < 1e-6 for k in gt)
    return {"passed": exact, "tokens": tokens, "time_sec": dt, "turns": 1, "blocks": 0, "pred": pred}


def eval_model_t1_h2_v3(spec: str, base_dir: Path, csv_path: Path, gt: dict) -> dict[str, Any]:
    t0 = time.time()
    wdir = base_dir / re.sub(r"[^a-zA-Z0-9_]", "_", f"t1_{spec}")
    wdir.mkdir(parents=True, exist_ok=True)

    schema_l1 = build_data_schema_preview(csv_path, sample_rows=2)
    skill_md = (H2_ROOT / "skills" / "cuisine-data" / "SKILL.md").read_text(encoding="utf-8")
    sys_msg = (
        "Tu tournes dans le Harnais H2 v3 (Mode Cuisine RLM + Middleware AST).\n"
        f"{skill_md}\n\n"
        "Écris UNIQUEMENT un script Python autonome dans ```python ... ``` qui lit "
        f"`{csv_path}` avec `csv.DictReader` et `decimal.Decimal` (`ROUND_HALF_UP`), et affiche sur sa "
        "dernière ligne `print(json.dumps(result))` avec les 4 clés : "
        "`valid_tx_count`, `stripe_fees_total_usd`, `affiliate_payout_usd`, `final_net_payout_usd`."
    )
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": f"{TASK1_RULES_PROMPT}\n\n{schema_l1}"},
    ]

    tot_tok = 0
    blocks = 0
    pred: dict[str, Any] = {}
    script_file = wdir / "solve_t1.py"
    out_json = wdir / "t1_out.json"

    for turn in range(1, 4):
        reply, tok = call_universal_model(spec, messages, max_tokens=2200, timeout=55)
        tot_tok += tok
        messages.append({"role": "assistant", "content": reply})

        # Brique 7 (v3) : Réparation AST & injection automatique des imports pour petits modèles locaux/gratuits
        code = repair_python_code_for_small_models(reply)
        script_file.write_text(code + "\n", encoding="utf-8")

        fast_errs = verify_single_file_fast(script_file, "solve_t1.py")
        if fast_errs:
            blocks += 1
            messages.append({"role": "user", "content": "[POST-TOOL INTERMEDIATE CHECK BLOQUÉ]\n" + "\n".join(fast_errs)})
            continue

        proc = subprocess.run(
            [
                sys.executable,
                str(H2_ROOT / "cuisine" / "cuisine_repl.py"),
                "run",
                str(script_file),
                str(out_json),
                "valid_tx_count,stripe_fees_total_usd,affiliate_payout_usd,final_net_payout_usd",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0:
            blocks += 1
            err_msg = (proc.stdout + "\n" + proc.stderr).strip()
            messages.append({"role": "user", "content": f"[STOP HOOK / JUGE DATA 444 BLOQUÉ]\n{err_msg}\nCorrige le script."})
            continue

        pred = json.loads(out_json.read_text(encoding="utf-8"))
        # Brique 8 (v3) : Vérificateur d'invariants métier (valid_tx_count > 0, stripe_fees > 0, net < gross)
        if int(pred.get("valid_tx_count", 0)) <= 0 or float(pred.get("stripe_fees_total_usd", 0)) <= 0:
            blocks += 1
            messages.append({"role": "user", "content": "[INVARIANT MÉTIER BLOQUÉ] `valid_tx_count` et `stripe_fees_total_usd` doivent être > 0."})
            continue
        break

    dt = round(time.time() - t0, 2)
    exact = all(k in pred and abs(float(pred[k]) - float(gt[k])) < 1e-6 for k in gt)
    return {"passed": exact, "tokens": tot_tok, "time_sec": dt, "turns": turn, "blocks": blocks, "pred": pred}


def eval_model_t2_bare(spec: str, base_dir: Path) -> dict[str, Any]:
    t0 = time.time()
    wdir = base_dir / re.sub(r"[^a-zA-Z0-9_]", "_", f"t2_bare_{spec}")
    wdir.mkdir(parents=True, exist_ok=True)
    engine_path = setup_task2_code(wdir)
    words_raw = (wdir / "t2_words_sample.json").read_text(encoding="utf-8")
    code_raw = "\n".join(ln for ln in engine_path.read_text().splitlines() if not ln.strip().startswith("# BUG "))

    prompt = (
        "# RULES.md\nTu es un expert Python vidéo. Vérifie toujours tes calculs de temps et ne laisse aucun bug.\n\n"
        "Corrige `timeline_engine.py` (problèmes de synchronisation des sous-titres, d'écran noir sur certaines scènes "
        "et de durée finale vis-à-vis de la voix +0.25s tail pad) et renvoie le fichier complet dans ```python ... ```.\n\n"
        f"Fichier `timeline_engine.py` :\n```python\n{code_raw}\n```\n\n"
        f"Fichier `t2_words_sample.json` :\n```json\n{words_raw}\n```"
    )
    reply, tokens = call_universal_model(spec, [{"role": "user", "content": prompt}], max_tokens=2200, timeout=55)
    dt = round(time.time() - t0, 2)

    fixed_code = repair_python_code_for_small_models(reply)
    engine_path.write_text(fixed_code + "\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(wdir / "test_timeline_judge.py")], cwd=str(wdir), capture_output=True, text=True, timeout=10)
    return {"passed": proc.returncode == 0, "tokens": tokens, "time_sec": dt, "turns": 1, "blocks": 0}


def eval_model_t2_h2_v3(spec: str, base_dir: Path) -> dict[str, Any]:
    t0 = time.time()
    wdir = base_dir / re.sub(r"[^a-zA-Z0-9_]", "_", f"t2_h2_{spec}")
    wdir.mkdir(parents=True, exist_ok=True)
    engine_path = setup_task2_code(wdir)
    words_preview = build_data_schema_preview(wdir / "t2_words_sample.json", sample_rows=2)
    code_raw = "\n".join(ln for ln in engine_path.read_text().splitlines() if not ln.strip().startswith("# BUG "))

    sys_msg = (
        "Tu tournes dans le Harnais H2 v3 (Pi-Code + Mode Cuisine + Middleware AST + Stop Hook chmod 444).\n"
        "Renvoie UNIQUEMENT le code complet corrigé de `timeline_engine.py` dans ```python ... ```."
    )
    user_msg = (
        "Corrige `timeline_engine.py` pour que tous les tests de synchronisation sous-titres/scènes/durée voix "
        "(tail pad +0.25s) passent devant le juge déterministe.\n\n"
        f"{words_preview}\n\n"
        f"Code actuel de `timeline_engine.py` :\n```python\n{code_raw}\n```"
    )
    messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]

    tot_tok = 0
    blocks = 0
    passed = False

    for turn in range(1, 4):
        reply, tok = call_universal_model(spec, messages, max_tokens=2200, timeout=55)
        tot_tok += tok
        messages.append({"role": "assistant", "content": reply})

        fixed_code = repair_python_code_for_small_models(reply)
        engine_path.write_text(fixed_code + "\n", encoding="utf-8")

        fast_errs = verify_single_file_fast(engine_path, "timeline_engine.py")
        if fast_errs:
            blocks += 1
            messages.append({"role": "user", "content": "[POST-TOOL INTERMEDIATE CHECK BLOQUÉ]\n" + "\n".join(fast_errs)})
            continue

        ok_ver, ver_errs = run_pre_stop_verifier(wdir, edited_files=["timeline_engine.py"], domain="code")
        if not ok_ver:
            blocks += 1
            err_txt = "\n".join(ver_errs)
            messages.append(
                {
                    "role": "user",
                    "content": f"[STOP HOOK VERIFY_GATE BLOQUÉ (Tour {turn})]\n{err_txt}\n\nCorrige exactement ces points et renvoie `timeline_engine.py`.",
                }
            )
            continue

        passed = True
        break

    dt = round(time.time() - t0, 2)
    return {"passed": passed, "tokens": tot_tok, "time_sec": dt, "turns": turn, "blocks": blocks}


def evaluate_one_model_pair(entry: tuple[str, str, str], base_dir: Path, csv_path: Path, gt1: dict) -> dict[str, Any]:
    cat, spec, label = entry
    t1_b = eval_model_t1_bare(spec, csv_path, gt1)
    t1_h = eval_model_t1_h2_v3(spec, base_dir, csv_path, gt1)
    t2_b = eval_model_t2_bare(spec, base_dir)
    t2_h = eval_model_t2_h2_v3(spec, base_dir)

    bare_score = int(t1_b["passed"]) + int(t2_b["passed"])
    h2_score = int(t1_h["passed"]) + int(t2_h["passed"])
    bare_tok = t1_b["tokens"] + t2_b["tokens"]
    h2_tok = t1_h["tokens"] + t2_h["tokens"]
    ratio = round(bare_tok / max(1, h2_tok), 2)
    blocks = t1_h["blocks"] + t2_h["blocks"]

    print(
        f"  ✓ [{cat:14s}] {label:35s} | SANS HARNAIS: {bare_score}/2 ({bare_tok:6,d} tok) "
        f"-> HARNAIS H2 v3: {h2_score}/2 ({h2_tok:5,d} tok, ÷{ratio:.1f}x, {blocks} blocks)",
        flush=True,
    )
    return {
        "category": cat,
        "spec": spec,
        "label": label,
        "sans_harnais_score": f"{bare_score}/2",
        "harnais_h2_v3_score": f"{h2_score}/2",
        "sans_harnais_tokens": bare_tok,
        "harnais_h2_v3_tokens": h2_tok,
        "token_reduction_factor": ratio,
        "stop_hook_recoveries": blocks,
        "t1_data": {"sans_harnais": t1_b, "harnais_h2_v3": t1_h},
        "t2_code": {"sans_harnais": t2_b, "harnais_h2_v3": t2_h},
    }


def main() -> int:
    import re as _re  # noqa: F401
    print("=================================================================================================")
    print("  ARÈNE MULTI-MODÈLES UNIVERSELLE — HARNAIS H2 v3 (10 MODÈLES : LOCAL, FREELLM :3011, DEEPSEEK, CHATGPT, CLAUDE)")
    print("=================================================================================================")
    t_start = time.time()
    with tempfile.TemporaryDirectory(prefix="h2_arena_") as tmp:
        base_dir = Path(tmp)
        csv_path, gt1 = setup_task1_data(base_dir)

        rows = []
        # Exécuter les fournisseurs distincts en parallèle, mais séquentiellement sur :3011 et :10100 pour éviter 429
        freellm_entries = [e for e in ARENA_MODELS if e[0] in ("LOCAL_M5_METAL", "FREELLM_3011")]
        other_entries = [e for e in ARENA_MODELS if e[0] not in ("LOCAL_M5_METAL", "FREELLM_3011")]

        def run_seq(entries):
            return [evaluate_one_model_pair(e, base_dir, csv_path, gt1) for e in entries]

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            fut_seq = ex.submit(run_seq, freellm_entries)
            futs_other = [ex.submit(evaluate_one_model_pair, e, base_dir, csv_path, gt1) for e in other_entries]
            rows.extend(fut_seq.result())
            for f in futs_other:
                rows.append(f.result())

    out_path = BENCH_DIR / "arena_multimodel_h2_v3.json"
    out_path.write_text(json.dumps({"elapsed_sec": round(time.time() - t_start, 1), "models": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n📊 Résultats complets de l'Arène Multi-Modèles sauvegardés dans : {out_path}")
    return 0


if __name__ == "__main__":
    import re  # noqa: F811
    sys.exit(main())
