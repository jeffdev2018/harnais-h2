#!/usr/bin/env python3
"""
BANC D'ESSAI OFFICIEL 100 TÂCHES (T001 -> T100) — HARNAIS H2 v3
10 Paliers progressifs de 10 tâches chacun (de Niveau 1 Ultra-Simple à Niveau 10 Boss Final) :
  - Chaque palier k (k = 1..10) contient :
      * 4 tâches DATA_CUISINE (CSV financiers/opérations de taille 50 + 40*k lignes et complexité k)
      * 3 tâches CODE_ALGO    (module Python algorithmique/harnais avec bugs de niveau k)
      * 3 tâches VIDEO_STUDIO (moteur timeline/sous-titres/scènes + `words.json` de 60 + 50*k mots)
  - Total = 100 tâches distinctes (40 Data Mode Cuisine + 30 Code Algo + 30 Vidéo Studio)
  - Évalue :
      1) La courbe intégrale sur les 100 tâches (200 exécutions : SANS HARNAIS vs HARNAIS H2 v3)
      2) Le banc multi-modèles stratifié sur les 10 paliers avec TOUS les moteurs du Mac :
         - Local M5 Pro Metal (`local:gemma-4-e2b-it-qat:gguf:q4`)
         - FreeLLMAPI :3011 (`freellm:auto` & `freellm:qwen3.8-27b`, $0.00)
         - DeepSeek (`deepseek:deepseek-chat`)
         - Claude (`cli:claude`)
         - ChatGPT (`cli:codex`)
         - Cascade H2 v3 (`Local 2B -> FreeLLM $0 -> DeepSeek/Claude` sous contrôle du Juge chmod 444)
"""
from __future__ import annotations

import concurrent.futures
import csv
import datetime
import json
import os
import random
import re
import stat
import subprocess
import sys
import tempfile
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
H2_ROOT = BENCH_DIR.parent
sys.path.insert(0, str(H2_ROOT / "core"))

from context_mgr import build_data_schema_preview  # noqa: E402
from providers import call_universal_model, classify_task_complexity, repair_python_code_for_small_models  # noqa: E402
from verify import run_pre_stop_verifier, verify_single_file_fast  # noqa: E402


def d2(val: object) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def f2(val: object) -> float:
    return float(d2(val))


def norm_gmail(email: str) -> str:
    email = email.strip().lower()
    local, _, domain = email.partition("@")
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+")[0].replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def extract_json_obj(text: str) -> dict[str, Any]:
    for cand in re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)[::-1]:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


# =============================================================================
# DÉFINITION DES 100 TÂCHES (T001 -> T100) À TRAVERS 10 NIVEAUX DE DIFFICULTÉ
# =============================================================================
LEVEL_DESCRIPTIONS = {
    1: "Niveau 1 (Trivial : 1 opération directe, petits fichiers)",
    2: "Niveau 2 (Simple : 1 filtre conditionnel simple)",
    3: "Niveau 3 (Élémentaire : 2 conditions ou remise fixe)",
    4: "Niveau 4 (Intermédiaire - : pourcentages arrondis par ligne)",
    5: "Niveau 5 (Intermédiaire + : frais fixes + variables + remboursements)",
    6: "Niveau 6 (Avancé - : multi-devises FX + paliers de remise)",
    7: "Niveau 7 (Avancé + : déduplication temporelle <15m + alias Gmail)",
    8: "Niveau 8 (Complexe : doublons Gmail + FX + pénalités de litige $15)",
    9: "Niveau 9 (Très Complexe : 5 règles croisées + commissions affiliés)",
    10: "Niveau 10 (Boss Final : réconciliation intégrale 450 lignes / 560 mots + révocation par ref_tx_id)",
}


def generate_100_task_specs() -> list[dict[str, Any]]:
    """Construit le catalogue ordonné des 100 tâches T001..T100 (10 tâches par niveau 1..10)."""
    specs: list[dict[str, Any]] = []
    idx = 1
    for level in range(1, 11):
        # 4 tâches DATA_CUISINE par niveau (40 au total)
        for sub in range(1, 5):
            tid = f"T{idx:03d}"
            n_rows = 50 + level * 38 + sub * 5
            specs.append({
                "id": tid,
                "num": idx,
                "level": level,
                "sub": sub,
                "domain": "DATA_CUISINE",
                "n_rows": n_rows,
                "title": f"L{level:02d}-Data#{sub} ({n_rows} lignes CSV · {LEVEL_DESCRIPTIONS[level].split(':')[1].strip(' )')})",
            })
            idx += 1

        # 3 tâches CODE_ALGO par niveau (30 au total)
        for sub in range(1, 4):
            tid = f"T{idx:03d}"
            specs.append({
                "id": tid,
                "num": idx,
                "level": level,
                "sub": sub,
                "domain": "CODE_ALGO",
                "n_items": 40 + level * 25 + sub * 10,
                "title": f"L{level:02d}-Code#{sub} (Module Python Algo · {min(4, (level + 1) // 2)} bug(s))",
            })
            idx += 1

        # 3 tâches VIDEO_STUDIO par niveau (30 au total)
        for sub in range(1, 4):
            tid = f"T{idx:03d}"
            n_words = ((60 + level * 48 + sub * 8) // 4) * 4
            specs.append({
                "id": tid,
                "num": idx,
                "level": level,
                "sub": sub,
                "domain": "VIDEO_STUDIO",
                "n_words": n_words,
                "title": f"L{level:02d}-Video#{sub} (Timeline Short {n_words} mots JSON · {min(4, (level + 1) // 2)} invariant(s))",
            })
            idx += 1
    return specs


# =============================================================================
# 1. CONSTRUCTEUR & VÉRITÉ TERRAIN DES 40 TÂCHES DATA_CUISINE (Niveaux 1..10)
# =============================================================================
def materialize_data_task(spec: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    tid = spec["id"]
    level = spec["level"]
    sub = spec["sub"]
    n_rows = spec["n_rows"]
    rng = random.Random(spec["num"] * 7919 + 20261124)

    csv_path = work_dir / f"{tid.lower()}_data.csv"
    emails = [
        "alex.martin@gmail.com",
        "alexmartin+promo@gmail.com",
        "a.l.e.x.martin@gmail.com",
        "claire.dubois@studio.fr",
        "jean.dupont@gmail.com",
        "jeandupont+vip@gmail.com",
        "lucas.dev@cyber.io",
        "sophia.rossi@gmail.com",
        "sophiarossi+yt@gmail.com",
    ]
    plans = ["STARTER", "PRO", "ENTERPRISE"]
    currencies = ["USD", "USD", "EUR", "GBP"]
    affs = ["", "", "AFF_JEFF", "AFF_PARTNER", ""]

    rows: list[list[str]] = []
    paid_pool: list[list[str]] = []
    base_ts = datetime.datetime(2026, 10, 1, 8, 0)
    tx_idx = 1

    target_paid = int(n_rows * (0.95 if level <= 4 else 0.82))
    while len(rows) < target_paid:
        em = rng.choice(emails)
        amt = f"{rng.choice([15.00, 25.00, 49.00, 79.00, 99.00, 120.00, 149.00, 199.00]):.2f}"
        disc = f"{rng.choice([0.00, 5.00, 10.00]):.2f}"
        plan = rng.choice(plans)
        curr = "USD" if level <= 5 else rng.choice(currencies)
        aff = rng.choice(affs)
        ts = base_ts + datetime.timedelta(minutes=tx_idx * 30 + rng.randint(1, 10))
        row = [f"TX_{tx_idx:04d}", ts.strftime("%Y-%m-%d %H:%M"), em, amt, disc, plan, curr, "PAID", aff, ""]
        rows.append(row)
        paid_pool.append(row)
        tx_idx += 1

        if level >= 7 and rng.random() < 0.14 and len(rows) < target_paid:
            alias_em = em.replace("@gmail.com", "+dup@gmail.com") if "gmail.com" in em else em
            dup_ts = ts + datetime.timedelta(minutes=rng.choice([2, 6, 11]))
            rows.append([f"TX_{tx_idx:04d}", dup_ts.strftime("%Y-%m-%d %H:%M"), alias_em, amt, disc, plan, curr, "PAID", aff, ""])
            tx_idx += 1

    rem = n_rows - len(rows)
    for k in range(max(0, rem)):
        orig = rng.choice(paid_pool)
        st = "DISPUTE" if (level >= 8 and k % 3 == 0) else "REFUND"
        r_ts = datetime.datetime.strptime(orig[1], "%Y-%m-%d %H:%M") + datetime.timedelta(days=1, minutes=k * 5)
        rows.append([f"TX_{tx_idx:04d}", r_ts.strftime("%Y-%m-%d %H:%M"), orig[2], orig[3], "0.00", orig[5], orig[6], st, orig[8], orig[0]])
        tx_idx += 1

    rows.sort(key=lambda r: r[1])
    header = ["tx_id", "timestamp", "email", "amount_usd", "discount_usd", "plan", "currency", "status", "affiliate", "ref_tx_id"]
    csv_path.write_text("\n".join([",".join(header)] + [",".join(r) for r in rows]), encoding="utf-8")

    with csv_path.open("r", encoding="utf-8") as f:
        dict_rows = list(csv.DictReader(f))

    valid_count = 0
    net_total = Decimal("0.00")

    if level == 1:
        # Niveau 1 : somme simple de amount_usd sur les lignes PAID
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                net_total += Decimal(r["amount_usd"])
        rule_desc = "Calcule la somme exacte de `amount_usd` pour toutes les lignes où `status == 'PAID'`."
    elif level == 2:
        # Niveau 2 : filtre sur status == PAID et plan == PRO (ou ENTERPRISE selon sub)
        target_p = "PRO" if sub % 2 == 1 else "ENTERPRISE"
        for r in dict_rows:
            if r["status"] == "PAID" and r["plan"] == target_p:
                valid_count += 1
                net_total += Decimal(r["amount_usd"])
        rule_desc = f"Calcule la somme exacte de `amount_usd` uniquement pour les lignes où `status == 'PAID'` et `plan == '{target_p}'`."
    elif level == 3:
        # Niveau 3 : PAID moins discount_usd
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                net_total += Decimal(r["amount_usd"]) - Decimal(r["discount_usd"])
        rule_desc = "Pour chaque ligne `status == 'PAID'`, calcule `amount_usd - discount_usd` et fais la somme."
    elif level == 4:
        # Niveau 4 : taxe ou remise en % par ligne arrondie au centime
        rate = Decimal("0.90") if sub % 2 == 1 else Decimal("1.08")
        label_r = "une remise de 10% (`amount_usd * 0.90`)" if sub % 2 == 1 else "une taxe de 8% (`amount_usd * 1.08`)"
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                net_total += d2(Decimal(r["amount_usd"]) * rate)
        rule_desc = f"Pour chaque ligne `status == 'PAID'`, applique {label_r} arrondie au centime (`ROUND_HALF_UP`) ligne par ligne."
    elif level == 5:
        # Niveau 5 : frais Stripe 2.9% + $0.30 par ligne PAID, moins REFUND
        for r in dict_rows:
            amt = Decimal(r["amount_usd"])
            if r["status"] == "PAID":
                valid_count += 1
                fee = d2(amt * Decimal("0.029") + Decimal("0.30"))
                net_total += amt - fee
            elif r["status"] == "REFUND":
                net_total -= amt
        rule_desc = (
            "1) Pour chaque ligne `status == 'PAID'`, déduis les frais Stripe `fee = round_half_up(amount_usd * 0.029 + 0.30, 2)`.\n"
            "2) Pour chaque ligne `status == 'REFUND'`, soustrais `amount_usd` du total (les frais Stripe initiaux ne sont pas remboursés)."
        )
    elif level == 6:
        # Niveau 6 : Frais Stripe + Frais FX 1.5% hors USD + Refunds
        for r in dict_rows:
            amt = Decimal(r["amount_usd"])
            if r["status"] == "PAID":
                valid_count += 1
                base_fee = d2(amt * Decimal("0.029") + Decimal("0.30"))
                fx_fee = d2(amt * Decimal("0.015")) if r["currency"] != "USD" else Decimal("0.00")
                net_total += amt - (base_fee + fx_fee)
            elif r["status"] == "REFUND":
                net_total -= amt
        rule_desc = (
            "1) Pour chaque ligne `status == 'PAID'`, calcule `base_fee = round_half_up(amount_usd * 0.029 + 0.30, 2)` et "
            "`fx_fee = round_half_up(amount_usd * 0.015, 2)` si `currency != 'USD'` (sinon `0.00`), puis ajoute `amount_usd - (base_fee + fx_fee)`.\n"
            "2) Soustrais `amount_usd` de chaque ligne `status == 'REFUND'`."
        )
    elif level == 7:
        # Niveau 7 : Déduplication Gmail < 900s + Frais Stripe 2.9% + $0.30
        last_seen: dict[tuple[str, str], datetime.datetime] = {}
        for r in dict_rows:
            ts = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M")
            amt = Decimal(r["amount_usd"])
            if r["status"] == "PAID":
                key = (norm_gmail(r["email"]), r["amount_usd"])
                if key in last_seen and (ts - last_seen[key]).total_seconds() < 900:
                    continue
                last_seen[key] = ts
                valid_count += 1
                fee = d2(amt * Decimal("0.029") + Decimal("0.30"))
                net_total += amt - fee
        rule_desc = (
            "1) Normalise `email` (minuscules ; si `@gmail.com`/`@googlemail.com`, retire `+tag` et tous les `.` avant `@`). "
            "Ignore toute ligne `PAID` ayant le même `(email_norm, amount_usd)` à moins de 900 secondes (`< 900s`) de la dernière ligne `PAID` acceptée pour cette clé.\n"
            "2) Sur chaque `PAID` retenue, déduis `fee = round_half_up(amount_usd * 0.029 + 0.30, 2)`."
        )
    elif level == 8:
        # Niveau 8 : Doublons Gmail <900s + Frais Stripe + FX 1.5% + Refunds + Litiges ($15)
        last_seen = {}
        for r in dict_rows:
            ts = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M")
            amt = Decimal(r["amount_usd"])
            if r["status"] == "PAID":
                key = (norm_gmail(r["email"]), r["amount_usd"])
                if key in last_seen and (ts - last_seen[key]).total_seconds() < 900:
                    continue
                last_seen[key] = ts
                valid_count += 1
                fee = d2(amt * Decimal("0.029") + Decimal("0.30")) + (d2(amt * Decimal("0.015")) if r["currency"] != "USD" else Decimal("0.00"))
                net_total += amt - fee
            elif r["status"] == "REFUND":
                net_total -= amt
            elif r["status"] == "DISPUTE":
                net_total -= amt + Decimal("15.00")
        rule_desc = (
            "1) Filtre les doublons `PAID` même `(email_norm Gmail, amount_usd)` à `< 900s` de la dernière ligne `PAID` acceptée.\n"
            "2) Sur chaque `PAID` retenue, déduis `base_fee = round_half_up(amount_usd * 0.029 + 0.30, 2)` et `fx_fee = round_half_up(amount_usd * 0.015, 2)` si `currency != 'USD'`.\n"
            "3) Soustrais `amount_usd` pour chaque `REFUND` et `amount_usd + 15.00` pour chaque `DISPUTE`."
        )
    elif level == 9:
        # Niveau 9 : Doublons Gmail <900s + Frais Stripe + FX + Commission affilié 18% sur net PAID
        last_seen = {}
        for r in dict_rows:
            ts = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M")
            amt = Decimal(r["amount_usd"])
            if r["status"] == "PAID":
                key = (norm_gmail(r["email"]), r["amount_usd"])
                if key in last_seen and (ts - last_seen[key]).total_seconds() < 900:
                    continue
                last_seen[key] = ts
                valid_count += 1
                fee = d2(amt * Decimal("0.029") + Decimal("0.30")) + (d2(amt * Decimal("0.015")) if r["currency"] != "USD" else Decimal("0.00"))
                net_tx = amt - fee
                aff_cut = d2(net_tx * Decimal("0.18")) if r["affiliate"].strip() else Decimal("0.00")
                net_total += net_tx - aff_cut
            elif r["status"] == "REFUND":
                net_total -= amt
            elif r["status"] == "DISPUTE":
                net_total -= amt + Decimal("15.00")
        rule_desc = (
            "1) Filtre les doublons `PAID` même `(email_norm Gmail, amount_usd)` à `< 900s` de la dernière ligne `PAID` acceptée.\n"
            "2) Sur chaque `PAID` retenue, `fee = round_half_up(amount_usd * 0.029 + 0.30, 2) + (round_half_up(amount_usd * 0.015, 2) si currency != 'USD' sinon 0)` et `net_tx = amount_usd - fee`.\n"
            "3) Si `affiliate` est non vide sur cette ligne `PAID`, déduis aussi `round_half_up(net_tx * 0.18, 2)`.\n"
            "4) Soustrais `amount_usd` pour chaque `REFUND` et `amount_usd + 15.00` pour chaque `DISPUTE`."
        )
    else:
        # Niveau 10 (Boss Final) : 5 règles croisées + révocation d'affilié (20% du net) par ref_tx_id
        last_seen = {}
        valid_paid: dict[str, dict[str, Any]] = {}
        rev_ids: set[str] = set()
        ref_sum = Decimal("0.00")
        disp_sum = Decimal("0.00")
        for r in dict_rows:
            ts = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M")
            amt = Decimal(r["amount_usd"])
            if r["status"] == "PAID":
                key = (norm_gmail(r["email"]), r["amount_usd"])
                if key in last_seen and (ts - last_seen[key]).total_seconds() < 900:
                    continue
                last_seen[key] = ts
                fee = d2(amt * Decimal("0.029") + Decimal("0.30")) + (d2(amt * Decimal("0.015")) if r["currency"] != "USD" else Decimal("0.00"))
                valid_paid[r["tx_id"]] = {"gross": amt, "fee": fee, "net": amt - fee, "aff": r["affiliate"].strip()}
            elif r["status"] == "REFUND":
                rev_ids.add(r["ref_tx_id"].strip())
                ref_sum += amt
            elif r["status"] == "DISPUTE":
                rev_ids.add(r["ref_tx_id"].strip())
                disp_sum += amt + Decimal("15.00")
        valid_count = len(valid_paid)
        gross_s = sum((v["gross"] for v in valid_paid.values()), Decimal("0.00"))
        fee_s = sum((v["fee"] for v in valid_paid.values()), Decimal("0.00"))
        aff_s = sum(
            (d2(v["net"] * Decimal("0.20")) for tx_id, v in valid_paid.items() if v["aff"] and tx_id not in rev_ids),
            Decimal("0.00"),
        )
        net_total = gross_s - fee_s - ref_sum - disp_sum - aff_s
        rule_desc = (
            "1) Filtre les doublons `PAID` même `(email_norm Gmail, amount_usd)` à `< 900s` de la dernière ligne `PAID` acceptée.\n"
            "2) Sur chaque `PAID` retenue, `fee = round_half_up(amount_usd * 0.029 + 0.30, 2) + (round_half_up(amount_usd * 0.015, 2) si currency != 'USD' sinon 0)`.\n"
            "3) `REFUND` soustrait `amount_usd` ; `DISPUTE` soustrait `amount_usd + 15.00`.\n"
            "4) Pour chaque `PAID` retenue avec `affiliate` non vide ET dont le `tx_id` n'apparaît dans le `ref_tx_id` d'aucun `REFUND` ni `DISPUTE`, soustrais la commission affilié `round_half_up((amount_usd - fee) * 0.20, 2)`."
        )

    return {
        **spec,
        "csv_path": csv_path,
        "rule_desc": rule_desc,
        "ground_truth": {"valid_count": valid_count, "net_total_usd": f2(net_total)},
    }


# =============================================================================
# 2. CONSTRUCTEUR & JUGE CHMOD 444 DES 30 TÂCHES CODE_ALGO (Niveaux 1..10)
# =============================================================================
def materialize_code_algo_task(spec: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    level = spec["level"]
    n_items = spec["n_items"]

    # Fichier de contexte L3 pour activer le Mode Cuisine
    items = [{"id": f"ITEM_{i:04d}", "score": round(10.0 + (i * 3.7) % 90.0, 2), "active": (i % 5 != 0), "tokens": 120 + (i * 17) % 400} for i in range(n_items)]
    ctx_json = work_dir / "items_context.json"
    ctx_json.write_text(json.dumps(items, indent=2), encoding="utf-8")

    # Nombre de bugs gradué de 1 (Niveaux 1..3) à 4 (Niveaux 9..10)
    b1 = "-" if level >= 1 else "+"  # Bug 1 : soustraction au lieu d'addition dans total_active_score
    b2 = "if it.get('active') is False:" if level >= 4 else "if it.get('active') is True:"  # Bug 2 : filtre inversé
    b3 = "int(total_tokens / max_budget)" if level >= 7 else "round(total_tokens / max_budget * 100.0, 2)"  # Bug 3 : formule pct
    b4 = "len(items)" if level >= 9 else "len(active_items)"  # Bug 4 : dénominateur moyenne

    buggy_py = f'''#!/usr/bin/env python3
from __future__ import annotations
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def r2(val: float | Decimal) -> float:
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def analyze_items(json_path: Path, max_budget: int = 50000) -> dict:
    items = json.loads(json_path.read_text(encoding="utf-8"))
    active_items = []
    for it in items:
        {b2}
            active_items.append(it)

    total_score = Decimal("0.00")
    total_tokens = 0
    for it in active_items:
        total_score = total_score {b1} Decimal(str(it["score"]))
        total_tokens += int(it["tokens"])

    avg_score = r2(total_score / Decimal(str(max(1, {b4}))))
    budget_pct = r2({b3})
    return {{
        "active_count": len(active_items),
        "total_score": r2(total_score),
        "avg_score": avg_score,
        "budget_pct": budget_pct,
    }}
'''
    mod_path = work_dir / "algo_module.py"
    mod_path.write_text(buggy_py, encoding="utf-8")

    # Vérité terrain déterministe pour le juge chmod 444
    act = [it for it in items if it["active"] is True]
    gt_count = len(act)
    gt_tot = float(d2(sum(Decimal(str(it["score"])) for it in act)))
    gt_avg = float(d2(Decimal(str(gt_tot)) / Decimal(str(max(1, gt_count)))))
    gt_pct = float(d2(Decimal(str(sum(it["tokens"] for it in act))) / Decimal("50000") * Decimal("100.0")))

    judge_py = f'''#!/usr/bin/env python3
import sys
from pathlib import Path
from algo_module import analyze_items

res = analyze_items(Path(__file__).resolve().parent / "items_context.json", max_budget=50000)
errs = []
if res.get("active_count") != {gt_count}:
    errs.append(f"active_count attendu {gt_count} (items avec active==True), obtenu {{res.get('active_count')}}")
if res.get("total_score") != {gt_tot}:
    errs.append(f"total_score attendu {gt_tot} (somme des scores actifs), obtenu {{res.get('total_score')}}")
if res.get("avg_score") != {gt_avg}:
    errs.append(f"avg_score attendu {gt_avg} (total_score / active_count), obtenu {{res.get('avg_score')}}")
if res.get("budget_pct") != {gt_pct}:
    errs.append(f"budget_pct attendu {gt_pct} (r2(total_tokens / max_budget * 100.0)), obtenu {{res.get('budget_pct')}}")

if errs:
    print("ÉCHEC JUGE ALGO 444 : " + " | ".join(errs))
    sys.exit(1)
print("JUGE ALGO 444 OK")
sys.exit(0)
'''
    j_path = work_dir / "test_judge.py"
    if j_path.exists():
        os.chmod(j_path, 0o644)
    j_path.write_text(judge_py, encoding="utf-8")
    os.chmod(j_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    sh_path = work_dir / ".harness_test.sh"
    sh_path.write_text("#!/usr/bin/env bash\npython3 test_judge.py\n", encoding="utf-8")
    os.chmod(sh_path, 0o755)

    return {**spec, "mod_path": mod_path, "ctx_path": ctx_json}


# =============================================================================
# 3. CONSTRUCTEUR & JUGE CHMOD 444 DES 30 TÂCHES VIDEO_STUDIO (Niveaux 1..10)
# =============================================================================
def materialize_video_task(spec: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    level = spec["level"]
    n_words = spec["n_words"]

    words = []
    t = 0.20
    for i in range(n_words):
        w_dur = 0.11
        gap = 0.03 if (i % 4 == 3) else 0.02
        words.append({
            "word": f"mot_{i}",
            "start": round(t, 2),
            "end": round(t + w_dur, 2),
            "confidence": 0.99,
            "speaker": "JEFF_VO",
            "waveform_meta": "studio-short-60fps-audio-sync-v3",
        })
        t += w_dur + gap

    voice_dur = round(max(t + 1.20, 42.40), 2)
    expected_total_dur = round(voice_dur + 0.25, 2)
    expected_wpm = round((n_words / expected_total_dur) * 60.0, 2)

    words_path = work_dir / "words_input.json"
    words_path.write_text(json.dumps(words, indent=2), encoding="utf-8")

    # Graduation des bugs de 1 (Niveaux 1..3) à 4 (Niveaux 9..10)
    pad_expr = "r2(chunk[-1]['end'] + 0.20)" if level >= 1 else "r2(min(chunk[-1]['end'] + 0.20, words[i + 4]['start'])) if (i + 4) < len(words) else r2(chunk[-1]['end'] + 0.20)"
    filt_code = "" if level >= 4 else "        if sc.get('duration', 0) <= 0 or sc.get('opacity', 1.0) <= 0:\n            continue\n"
    tail_code = (
        "    total_duration = clean_scenes[-1]['end'] if clean_scenes else 0.0\n"
        if level >= 7
        else (
            "    target_end = r2(voice_duration_sec + 0.25)\n"
            "    if clean_scenes and clean_scenes[-1]['end'] < target_end:\n"
            "        clean_scenes[-1]['end'] = target_end\n"
            "        clean_scenes[-1]['duration'] = r2(target_end - clean_scenes[-1]['start'])\n"
            "    total_duration = target_end\n"
        )
    )
    wpm_code = "r2((len(words) / voice_duration_sec) * 60.0)" if level >= 9 else "r2((len(words) / total_duration) * 60.0)"

    buggy_py = f'''#!/usr/bin/env python3
from __future__ import annotations
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def r2(val: float | Decimal) -> float:
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_timeline(words_json_path: Path, voice_duration_sec: float, raw_scenes: list[dict]) -> dict:
    words = json.loads(words_json_path.read_text(encoding="utf-8"))
    captions = []
    chunk_size = 4
    for i in range(0, len(words), chunk_size):
        chunk = words[i : i + chunk_size]
        if not chunk:
            continue
        start_t = r2(chunk[0]["start"])
        end_t = {pad_expr}
        captions.append({{
            "index": len(captions) + 1,
            "text": " ".join(w["word"].strip() for w in chunk),
            "start": start_t,
            "end": end_t,
        }})

    clean_scenes = []
    cursor = 0.0
    for sc in raw_scenes:
{filt_code}        dur = r2(sc["duration"])
        clean_scenes.append({{
            "id": sc["id"],
            "start": r2(cursor),
            "end": r2(cursor + dur),
            "duration": dur,
            "opacity": float(sc.get("opacity", 1.0)),
        }})
        cursor = r2(cursor + dur)

{tail_code}    wpm = {wpm_code}
    return {{
        "caption_count": len(captions),
        "captions": captions,
        "scenes": clean_scenes,
        "total_duration_sec": r2(total_duration),
        "wpm": wpm,
    }}
'''
    mod_path = work_dir / "timeline_engine.py"
    mod_path.write_text(buggy_py, encoding="utf-8")

    judge_py = f'''#!/usr/bin/env python3
import sys
from pathlib import Path
from timeline_engine import build_timeline

WORK_DIR = Path(__file__).resolve().parent
words_path = WORK_DIR / "words_input.json"
raw_scenes = [
    {{"id": "s1_hook", "duration": 10.0, "opacity": 1.0}},
    {{"id": "s_bad_zero", "duration": 0.0, "opacity": 1.0}},
    {{"id": "s_bad_neg", "duration": -2.0, "opacity": 0.9}},
    {{"id": "s_bad_black", "duration": 4.0, "opacity": 0.0}},
    {{"id": "s2_body", "duration": 15.0, "opacity": 1.0}},
    {{"id": "s3_outro", "duration": 10.0, "opacity": 0.95}},
]

res = build_timeline(words_path, voice_duration_sec={voice_dur}, raw_scenes=raw_scenes)
errors = []
caps = res.get("captions", [])
if len(caps) != {n_words // 4}:
    errors.append(f"Attendu {n_words // 4} sous-titres, obtenu {{len(caps)}}")
for idx in range(len(caps) - 1):
    if caps[idx]["end"] > caps[idx + 1]["start"]:
        errors.append(f"Overlap sous-titre #{{idx+1}} (end={{caps[idx]['end']}}) > #{{idx+2}} (start={{caps[idx+1]['start']}})")
        break
scenes = res.get("scenes", [])
if len(scenes) != 3:
    errors.append(f"Les scènes avec duration<=0 ou opacity<=0 doivent être filtrées : obtenu {{len(scenes)}} au lieu de 3")
if res.get("total_duration_sec") != {expected_total_dur} or (scenes and scenes[-1]["end"] != {expected_total_dur}):
    errors.append(f"total_duration_sec et scenes[-1]['end'] doivent valoir voice_duration_sec + 0.25 = {expected_total_dur}s, obtenu {{res.get('total_duration_sec')}}")
if res.get("wpm") != {expected_wpm}:
    errors.append(f"WPM attendu r2((len(words) / total_duration) * 60.0) = {expected_wpm}, obtenu {{res.get('wpm')}}")

if errors:
    print("ÉCHEC JUGE VIDEO 444 : " + " | ".join(errors))
    sys.exit(1)
print("JUGE VIDEO 444 OK")
sys.exit(0)
'''
    j_path = work_dir / "test_judge.py"
    if j_path.exists():
        os.chmod(j_path, 0o644)
    j_path.write_text(judge_py, encoding="utf-8")
    os.chmod(j_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    sh_path = work_dir / ".harness_test.sh"
    sh_path.write_text("#!/usr/bin/env bash\npython3 test_judge.py\n", encoding="utf-8")
    os.chmod(sh_path, 0o755)

    return {**spec, "mod_path": mod_path, "ctx_path": words_path}


# =============================================================================
# EXÉCUTEUR UNIVERSEL D'UNE TÂCHE (SANS HARNAIS vs HARNAIS H2 v3)
# =============================================================================
def run_single_task(spec: dict[str, Any], model_spec: str, mode: str, base_tmp: Path) -> dict[str, Any]:
    wdir = base_tmp / re.sub(r"[^a-zA-Z0-9_]", "_", f"{spec['id']}_{mode}_{model_spec}")
    wdir.mkdir(parents=True, exist_ok=True)
    dom = spec["domain"]
    t0 = time.time()

    if dom == "DATA_CUISINE":
        task = materialize_data_task(spec, wdir)
        csv_path = task["csv_path"]
        gt = task["ground_truth"]
        contract = (
            "Note sur `valid_count` : compte UNIQUEMENT les lignes `status == 'PAID'` retenues par le filtre "
            "(hors REFUND, DISPUTE et hors doublons ignorés)."
        )

        if mode == "SANS_HARNAIS":
            raw_csv = csv_path.read_text(encoding="utf-8")
            prompt = (
                f"# RULES.md\nSois précis et vérifie tes calculs.\n\n"
                f"Tâche {task['id']} ({task['title']}) :\n{task['rule_desc']}\n{contract}\n\n"
                f"CSV complet :\n```csv\n{raw_csv}\n```\n\n"
                "Réponds UNIQUEMENT par un JSON : `{\"valid_count\": <int>, \"net_total_usd\": <float>}`."
            )
            reply, tok = call_universal_model(model_spec, [{"role": "user", "content": prompt}], max_tokens=1800, timeout=45)
            pred = extract_json_obj(reply)
            passed = (
                "valid_count" in pred
                and "net_total_usd" in pred
                and int(pred["valid_count"]) == int(gt["valid_count"])
                and abs(float(pred["net_total_usd"]) - float(gt["net_total_usd"])) < 1e-6
            )
            return {"id": spec["id"], "level": spec["level"], "domain": dom, "model": model_spec, "mode": mode, "passed": passed, "tokens": tok, "time_sec": round(time.time() - t0, 2), "turns": 1, "blocks": 0}

        # Mode HARNAIS_H2_v3
        schema_l1 = build_data_schema_preview(csv_path, sample_rows=2)
        skill_md = (H2_ROOT / "skills" / "cuisine-data" / "SKILL.md").read_text(encoding="utf-8")
        sys_msg = (
            "Tu tournes dans le Harnais H2 v3 (Mode Cuisine RLM + Middleware AST).\n"
            f"{skill_md}\n\n"
            "Écris UNIQUEMENT un script Python autonome dans ```python ... ``` qui lit "
            f"`{csv_path}` avec `csv.DictReader` et `decimal.Decimal` (`ROUND_HALF_UP`), et affiche sur sa "
            "dernière ligne `print(json.dumps({\"valid_count\": valid_count, \"net_total_usd\": float(net_total)}))`."
        )
        messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": f"Tâche {task['id']} :\n{task['rule_desc']}\n{contract}\n\n{schema_l1}"}]
        tot_tok = 0
        blocks = 0
        pred = {}
        script_file = wdir / "solve.py"
        out_json = wdir / "out.json"

        for turn in range(1, 4):
            reply, tok = call_universal_model(model_spec, messages, max_tokens=2000, timeout=45)
            tot_tok += tok
            messages.append({"role": "assistant", "content": reply})
            code = repair_python_code_for_small_models(reply)
            script_file.write_text(code + "\n", encoding="utf-8")

            fast_errs = verify_single_file_fast(script_file, "solve.py")
            if fast_errs:
                blocks += 1
                messages.append({"role": "user", "content": "[POST-TOOL INTERMEDIATE CHECK BLOQUÉ]\n" + "\n".join(fast_errs)})
                continue

            proc = subprocess.run(
                [sys.executable, str(H2_ROOT / "cuisine" / "cuisine_repl.py"), "run", str(script_file), str(out_json), "valid_count,net_total_usd"],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode != 0:
                blocks += 1
                messages.append({"role": "user", "content": f"[STOP HOOK / JUGE 444 BLOQUÉ]\n{proc.stdout}\n{proc.stderr}\nCorrige le script."})
                continue
            pred = json.loads(out_json.read_text(encoding="utf-8"))
            break

        passed = (
            "valid_count" in pred
            and "net_total_usd" in pred
            and int(pred["valid_count"]) == int(gt["valid_count"])
            and abs(float(pred["net_total_usd"]) - float(gt["net_total_usd"])) < 1e-6
        )
        return {"id": spec["id"], "level": spec["level"], "domain": dom, "model": model_spec, "mode": mode, "passed": passed, "tokens": tot_tok, "time_sec": round(time.time() - t0, 2), "turns": turn, "blocks": blocks}

    # Domaines CODE_ALGO et VIDEO_STUDIO
    task = materialize_code_algo_task(spec, wdir) if dom == "CODE_ALGO" else materialize_video_task(spec, wdir)
    mod_path = task["mod_path"]
    ctx_path = task["ctx_path"]
    code_raw = mod_path.read_text(encoding="utf-8")

    if mode == "SANS_HARNAIS":
        ctx_raw = ctx_path.read_text(encoding="utf-8")
        prompt = (
            f"# RULES.md\nRelis attentivement ton code Python avant de répondre.\n\n"
            f"Tâche {task['id']} ({task['title']}) : Corrige tous les bugs dans `{mod_path.name}` "
            f"(filtrage, formules, non-chevauchement, durée ou moyennes) et renvoie le code complet dans ```python ... ```.\n\n"
            f"Code `{mod_path.name}` :\n```python\n{code_raw}\n```\n\n"
            f"Fichier `{ctx_path.name}` :\n```json\n{ctx_raw}\n```"
        )
        reply, tok = call_universal_model(model_spec, [{"role": "user", "content": prompt}], max_tokens=2000, timeout=45)
        mod_path.write_text(repair_python_code_for_small_models(reply) + "\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(wdir / "test_judge.py")], cwd=str(wdir), capture_output=True, text=True, timeout=10)
        return {"id": spec["id"], "level": spec["level"], "domain": dom, "model": model_spec, "mode": mode, "passed": proc.returncode == 0, "tokens": tok, "time_sec": round(time.time() - t0, 2), "turns": 1, "blocks": 0}

    # Mode HARNAIS_H2_v3
    ctx_preview = build_data_schema_preview(ctx_path, sample_rows=2)
    sys_msg = (
        "Tu tournes dans le Harnais H2 v3 (Pi-Code + Mode Cuisine + Middleware AST + Stop Hook chmod 444).\n"
        f"Renvoie UNIQUEMENT le fichier `{mod_path.name}` complet corrigé dans ```python ... ```."
    )
    user_msg = (
        f"Tâche {task['id']} ({task['title']}) : Corrige `{mod_path.name}` pour valider tous les invariants du juge déterministe.\n\n"
        f"{ctx_preview}\n\nCode `{mod_path.name}` :\n```python\n{code_raw}\n```"
    )
    messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]
    tot_tok = 0
    blocks = 0
    passed = False

    for turn in range(1, 4):
        reply, tok = call_universal_model(model_spec, messages, max_tokens=2000, timeout=45)
        tot_tok += tok
        messages.append({"role": "assistant", "content": reply})
        mod_path.write_text(repair_python_code_for_small_models(reply) + "\n", encoding="utf-8")

        fast_errs = verify_single_file_fast(mod_path, mod_path.name)
        if fast_errs:
            blocks += 1
            messages.append({"role": "user", "content": "[POST-TOOL INTERMEDIATE CHECK BLOQUÉ]\n" + "\n".join(fast_errs)})
            continue

        ok_ver, ver_errs = run_pre_stop_verifier(wdir, edited_files=[mod_path.name], domain="code")
        if not ok_ver:
            blocks += 1
            messages.append({"role": "user", "content": f"[STOP HOOK VERIFY_GATE BLOQUÉ (Tour {turn})]\n" + "\n".join(ver_errs) + f"\nCorrige `{mod_path.name}`."})
            continue
        passed = True
        break

    return {"id": spec["id"], "level": spec["level"], "domain": dom, "model": model_spec, "mode": mode, "passed": passed, "tokens": tot_tok, "time_sec": round(time.time() - t0, 2), "turns": turn, "blocks": blocks}


def run_cascade_h2_v3(spec: dict[str, Any], base_tmp: Path) -> dict[str, Any]:
    """
    Brique 9 + v4.3 — Cascade Économique H2 v4 avec Pré-Routeur de Complexité (<0.2 ms) :
    Utilise `classify_task_complexity` avant le Tour 1 :
      - Score faible (1..3) -> démarre sur Modèle Local 2B (`local:gemma-4-e2b-it-qat:gguf:q4`, $0.00)
      - Score moyen (4..7)  -> saute le 2B local, démarre sur `freellm:auto` ($0.00 sur :3011)
      - Score élevé (8..10) -> saute les petits modèles et démarre directement sur `deepseek:deepseek-chat` (0 tour perdu !)
    """
    # Construire un aperçu du prompt de la tâche pour que le pré-routeur <0.2ms mesure sa vraie complexité
    tmp_probe = base_tmp / f"probe_{spec['id']}"
    tmp_probe.mkdir(parents=True, exist_ok=True)
    if spec["domain"] == "DATA_CUISINE":
        t_info = materialize_data_task(spec, tmp_probe)
        route_decision = classify_task_complexity(t_info["rule_desc"], [t_info["csv_path"]])
    else:
        route_decision = classify_task_complexity(
            f"{spec['title']} " + (" ".join(f"{i}) rule" for i in range(1, spec["level"] + 1)))
            + (" gherkin rg- overlap blackdetect wpm ast security" if spec["level"] >= 8 else ""),
            [],
        )
    chain = route_decision["cascade_chain"]

    tot_tok = 0
    tot_blocks = 0
    t0 = time.time()
    winner = chain[-1]
    for m_spec in chain:
        res = run_single_task(spec, m_spec, "HARNAIS_H2_v3", base_tmp)
        tot_tok += res["tokens"]
        tot_blocks += res["blocks"]
        if res["passed"]:
            winner = m_spec
            return {
                **res,
                "model": "cascade:h2_v4",
                "pre_routed_tier": route_decision["recommended_tier"],
                "routing_ms": route_decision["routing_latency_ms"],
                "resolved_by": winner,
                "tokens": tot_tok,
                "blocks": tot_blocks,
                "time_sec": round(time.time() - t0, 2),
            }
    return {
        **res,
        "model": "cascade:h2_v4",
        "pre_routed_tier": route_decision["recommended_tier"],
        "routing_ms": route_decision["routing_latency_ms"],
        "resolved_by": winner,
        "tokens": tot_tok,
        "blocks": tot_blocks,
        "time_sec": round(time.time() - t0, 2),
    }


def main() -> int:
    specs = generate_100_task_specs()
    print("=====================================================================================================")
    print("  BANC D'ESSAI INTÉGRAL 100 TÂCHES (T001 -> T100) · NIVEAUX 1 À 10 · HARNAIS H2 v3")
    print("  40 Data Mode Cuisine + 30 Code Algo + 30 Vidéo Studio = 100 Tâches (200 Évaluations + Multi-Modèles)")
    print("=====================================================================================================")

    t_start = time.time()
    with tempfile.TemporaryDirectory(prefix="h2_100tasks_") as tmp:
        base_tmp = Path(tmp)

        # PARTIE 1 : Courbe intégrale des 100 tâches (200 exécutions : SANS HARNAIS vs HARNAIS H2 v3)
        jobs_100 = []
        for sp in specs:
            jobs_100.append((sp, "SANS_HARNAIS"))
            jobs_100.append((sp, "HARNAIS_H2_v3"))

        results_100: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            futs = [ex.submit(run_single_task, sp, "deepseek:deepseek-chat", m, base_tmp) for sp, m in jobs_100]
            done = 0
            for f in concurrent.futures.as_completed(futs):
                r = f.result()
                results_100.append(r)
                done += 1
                if done % 25 == 0 or done == len(jobs_100):
                    print(f"  [Courbe 100 Tâches : {done:3d}/{len(jobs_100)}] {r['id']} (L{r['level']:02d} {r['mode']:13s}) -> Pass={r['passed']} ({r['tokens']:,} tok)", flush=True)

        results_100.sort(key=lambda r: (int(r["id"][1:]), 0 if r["mode"] == "SANS_HARNAIS" else 1))

        print("\n=====================================================================================================")
        print("  PARTIE 1 — RÉSULTATS SUR LES 100 TÂCHES PAR NIVEAU DE DIFFICULTÉ (NIVEAU 1 -> NIVEAU 10)")
        print("=====================================================================================================")
        level_summaries = {}
        for lvl in range(1, 11):
            b_lvl = [r for r in results_100 if r["level"] == lvl and r["mode"] == "SANS_HARNAIS"]
            h_lvl = [r for r in results_100 if r["level"] == lvl and r["mode"] == "HARNAIS_H2_v3"]
            bp = sum(1 for r in b_lvl if r["passed"])
            hp = sum(1 for r in h_lvl if r["passed"])
            bt = sum(r["tokens"] for r in b_lvl)
            ht = sum(r["tokens"] for r in h_lvl)
            hb = sum(r["blocks"] for r in h_lvl)
            ratio = round(bt / max(1, ht), 2)
            level_summaries[lvl] = {
                "description": LEVEL_DESCRIPTIONS[lvl],
                "sans_harnais_pass": f"{bp}/10",
                "harnais_h2_v3_pass": f"{hp}/10",
                "sans_harnais_tokens": bt,
                "harnais_h2_v3_tokens": ht,
                "token_reduction_factor": ratio,
                "stop_hook_recoveries": hb,
            }
            print(
                f"  • Niveau {lvl:2d} (T{(lvl-1)*10+1:03d}..T{lvl*10:03d}) | SANS HARNAIS: {bp:2d}/10 ({bt:8,d} tok) "
                f"| HARNAIS H2 v3: {hp:2d}/10 ({ht:7,d} tok, ÷{ratio:.1f}x, {hb:2d} rattrapages StopHook)",
                flush=True,
            )

        all_b = [r for r in results_100 if r["mode"] == "SANS_HARNAIS"]
        all_h = [r for r in results_100 if r["mode"] == "HARNAIS_H2_v3"]
        t_bp = sum(1 for r in all_b if r["passed"])
        t_hp = sum(1 for r in all_h if r["passed"])
        t_bt = sum(r["tokens"] for r in all_b)
        t_ht = sum(r["tokens"] for r in all_h)
        t_hb = sum(r["blocks"] for r in all_h)
        t_rat = round(t_bt / max(1, t_ht), 2)
        print("-----------------------------------------------------------------------------------------------------")
        print(
            f"🏆 TOTAL 100 TÂCHES               | SANS HARNAIS: {t_bp:3d}/100 ({t_bp:3d}%, {t_bt:,} tok) "
            f"| HARNAIS H2 v3: {t_hp:3d}/100 ({t_hp:3d}%, {t_ht:,} tok, ÷{t_rat:.2f}x, {t_hb} rattrapages)",
            flush=True,
        )

        # PARTIE 2 : Évaluation Multi-Modèles Stratifiée sur l'échelle 1..10 (Local M5, FreeLLM :3011, DeepSeek, Claude, ChatGPT, Cascade)
        # On prend 5 tâches représentatives graduées (Niveau 1, Niveau 3, Niveau 5, Niveau 8, Niveau 10 Boss Final)
        ladder_specs = [specs[0], specs[25], specs[47], specs[71], specs[99]]
        print("\n=====================================================================================================")
        print("  PARTIE 2 — ÉCHELLE MULTI-MODÈLES (NIVEAUX 1 -> 10 : LOCAL M5, FREELLM :3011, DEEPSEEK, CLAUDE, CHATGPT, CASCADE)")
        print("=====================================================================================================")

        multi_models = [
            ("LOCAL_M5_METAL", "local:gemma-4-e2b-it-qat:gguf:q4", "Gemma 4 E2B Q4 (Local Apple M5 Pro)"),
            ("FREELLM_3011", "freellm:auto", "FreeLLM Auto (:3011 $0 -> Nemotron 550B)"),
            ("DEEPSEEK_API", "deepseek:deepseek-chat", "DeepSeek Chat V3/V4 Direct"),
            ("CLAUDE_CLI", "cli:claude", "Claude (via Claude Code CLI)"),
            ("CHATGPT_CLI", "cli:codex", "ChatGPT (via Codex CLI)"),
            ("CASCADE_H2_v3", "cascade:h2_v3", "Cascade H2 v3 (Local 2B -> FreeLLM $0 -> DeepSeek)"),
        ]

        multi_summary = []
        for cat, m_spec, label in multi_models:
            m_res = []
            for sp in ladder_specs:
                if m_spec == "cascade:h2_v3":
                    r = run_cascade_h2_v3(sp, base_tmp)
                else:
                    r = run_single_task(sp, m_spec, "HARNAIS_H2_v3", base_tmp)
                m_res.append(r)
            p_cnt = sum(1 for r in m_res if r["passed"])
            tok_s = sum(r["tokens"] for r in m_res)
            blk_s = sum(r["blocks"] for r in m_res)
            passed_lvls = [f"L{r['level']}:{'✓' if r['passed'] else '✗'}" for r in m_res]
            print(f"  • [{cat:14s}] {label:48s} -> {p_cnt}/5 ({' '.join(passed_lvls)}) | {tok_s:6,d} tok | {blk_s} blocks", flush=True)
            multi_summary.append({
                "category": cat,
                "model_spec": m_spec,
                "label": label,
                "passed_on_ladder": f"{p_cnt}/5",
                "ladder_breakdown": passed_lvls,
                "total_tokens": tok_s,
                "stop_hook_blocks": blk_s,
                "runs": m_res,
            })

    out_file = BENCH_DIR / "bench_results_100tasks_h2_v3.json"
    out_file.write_text(
        json.dumps(
            {
                "elapsed_sec": round(time.time() - t_start, 1),
                "total_tasks": 100,
                "global_100_summary": {
                    "sans_harnais_score": f"{t_bp}/100 ({t_bp}%)",
                    "harnais_h2_v3_score": f"{t_hp}/100 ({t_hp}%)",
                    "sans_harnais_tokens": t_bt,
                    "harnais_h2_v3_tokens": t_ht,
                    "token_reduction_factor": t_rat,
                    "stop_hook_recoveries": t_hb,
                },
                "levels_1_to_10": level_summaries,
                "multimodel_ladder": multi_summary,
                "details_100": results_100,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n📊 Rapport complet des 100 tâches + Échelle Multi-Modèles sauvegardé dans : {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
