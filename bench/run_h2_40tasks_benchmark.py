#!/usr/bin/env python3
"""
Banc d'Essai Progressif 40 Tâches (T01 -> T40) — Harnais H2 v2 vs Sans Harnais (RULES.md seul)
4 Paliers de difficulté croissante (10 tâches par palier : 5 Data/Finance Mode Cuisine + 5 Code/Vidéo/Studio) :
  - Palier 1 (T01..T10) : SIMPLE        (1 règle ou 1 bug isolé, ~90-120 lignes CSV / ~120 mots JSON)
  - Palier 2 (T11..T20) : INTERMÉDIAIRE (2 règles combinées ou 2 bugs, ~150-200 lignes CSV / ~200 mots JSON)
  - Palier 3 (T21..T30) : AVANCÉ        (3 règles + arrondis ligne par ligne + pièges Gmail/doublons, ~240-300 lignes)
  - Palier 4 (T31..T40) : EXTRÊME       (4-5 règles croisées, litiges, multi-devises, 4 bugs code/timeline imbriqués, ~350-450 lignes)

Chaque tâche est évaluée dans un répertoire isolé :
  1. Condition SANS HARNAIS : Fichier de données ou contexte JSON injecté en L1 + RULES.md, 1 tour sans Stop Hook.
  2. Condition HARNAIS H2 v2 : Mode Cuisine L1 (~120 tokens) + Exécution Python L2 + Détecteur AST Mode 4 +
                               Vérification intermédiaire PostToolUse + Stop Hook & Juge chmod 444 (jusqu'à 4 tours).
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
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
H2_ROOT = BENCH_DIR.parent
sys.path.insert(0, str(H2_ROOT / "core"))

from context_mgr import build_data_schema_preview  # noqa: E402
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


def load_api_credentials(model: str = "deepseek-chat") -> tuple[str, str]:
    ds_file = Path.home() / ".config/deepseek.key"
    if "deepseek" in model.lower() and ds_file.exists():
        return "https://api.deepseek.com/v1/chat/completions", ds_file.read_text().strip()
    auth_file = Path.home() / ".local/share/opencode/auth.json"
    if auth_file.exists():
        m = re.search(r"(sk-or-v1-[A-Za-z0-9]{40,})", auth_file.read_text())
        if m:
            return "https://openrouter.ai/api/v1/chat/completions", m.group(1)
    if ds_file.exists():
        return "https://api.deepseek.com/v1/chat/completions", ds_file.read_text().strip()
    raise RuntimeError("Clé API introuvable")


def call_llm(model: str, messages: list[dict[str, str]], max_tokens: int = 2500) -> tuple[str, int]:
    api_url, api_key = load_api_credentials(model)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://avelis.local",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=65) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"].get("content") or ""
            usage = body.get("usage") or {}
            tok = int(usage.get("total_tokens") or (len(json.dumps(messages)) // 4 + len(content) // 4))
            return content, tok
        except Exception as exc:
            if attempt == 1:
                return f'{{"error": "{exc}"}}', len(json.dumps(messages)) // 4
            time.sleep(1.5)
    return "{}", 0


def extract_code_block(text: str, lang: str = "python") -> str:
    m_lang = re.findall(rf"```{lang}\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if m_lang:
        return max(m_lang, key=len).strip()
    m_any = re.findall(r"```(?:\w+)?\s*(.*?)```", text, flags=re.DOTALL)
    if m_any:
        return max(m_any, key=len).strip()
    return text.strip()


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
# GÉNÉRATEUR PARAMÉTRIQUE DES 20 TÂCHES DATA (T01..T05, T11..T15, T21..T25, T31..T35)
# =============================================================================
DATA_SPECS = [
    # PALIER 1 — SIMPLE (1 règle franche, 90-110 lignes)
    ("T01", 1, "Simple : Total factures PAID", 90, 1, "Somme exacte de `amount_usd` pour les lignes où `status == 'PAID'`."),
    ("T02", 1, "Simple : Panier net après remise fixe", 95, 1, "Somme de `amount_usd` des lignes `status == 'PAID'` moins `discount_usd`."),
    ("T03", 1, "Simple : Revenu abonnements PRO", 100, 1, "Somme de `amount_usd` uniquement pour `plan == 'PRO'` et `status == 'PAID'`."),
    ("T04", 1, "Simple : Total dépenses en USD uniquement", 105, 1, "Somme de `amount_usd` pour `status == 'PAID'` et `currency == 'USD'`."),
    ("T05", 1, "Simple : Solde après remboursements directs", 110, 1, "Somme de `amount_usd` pour `status == 'PAID'` moins somme de `amount_usd` pour `status == 'REFUND'`."),
    # PALIER 2 — INTERMÉDIAIRE (2 règles combinées, 150-180 lignes)
    ("T11", 2, "Intermédiaire : Taxes 8.5% par ligne + Remboursements", 150, 2, "Pour chaque ligne `PAID`, ajoute une taxe de `8.5%` arrondie au centime (`round_half_up(amount_usd * 1.085, 2)`), puis soustrais le montant brut `amount_usd` des lignes `REFUND`."),
    ("T12", 2, "Intermédiaire : Frais FX 2.5% hors USD + Filtre PRO/TEAM", 160, 2, "Sur les lignes `PAID` dont `plan` est `PRO` ou `TEAM`, ajoute `2.5%` de frais FX arrondis ligne par ligne (`round_half_up(amount_usd * 1.025, 2)`) si `currency != 'USD'`."),
    ("T13", 2, "Intermédiaire : Frais processeur 2.9%+$0.30 par transaction", 165, 2, "Sur chaque ligne `PAID`, déduis les frais processeur `round_half_up(amount_usd * 0.029 + 0.30, 2)` pour obtenir le net."),
    ("T14", 2, "Intermédiaire : Commission affilié 15% sur brut PAID", 170, 2, "Sur chaque ligne `PAID`, si `affiliate != ''`, déduis une commission affilié de `round_half_up(amount_usd * 0.15, 2)` du montant brut."),
    ("T15", 2, "Intermédiaire : Remise -10% sur paniers >= $100 + Refunds", 180, 2, "Sur chaque ligne `PAID`, si `amount_usd >= 100.00`, applique une remise de `10%` (`round_half_up(amount_usd * 0.90, 2)`), puis soustrais `amount_usd` des lignes `REFUND`."),
    # PALIER 3 — AVANCÉ (3 règles : doublons Gmail <15m + Frais ligne par ligne + Refunds, 230-270 lignes)
    ("T21", 3, "Avancé : Déduplication Gmail <15m + Frais 2.9%+$0.30", 230, 3, "1) Normalise `email` (minuscules, si `@gmail.com`/`@googlemail.com` retire `.` et `+tag` avant `@`). Ignore toute ligne `PAID` doublon ayant même `(email_norm, amount_usd)` à `< 900s` de la précédente.\n2) Sur chaque `PAID` valide, déduis `fee = round_half_up(amount_usd * 0.029 + 0.30, 2)`."),
    ("T22", 3, "Avancé : Doublons Gmail + Frais FX 1.5% + Refunds non-remboursés", 240, 3, "1) Filtre les doublons `PAID` même `(email_norm, amount_usd)` à `< 900s`.\n2) Sur chaque `PAID` valide, `fee = round_half_up(amount_usd * 0.029 + 0.30, 2)` + (`round_half_up(amount_usd * 0.015, 2)` si `currency != 'USD'`).\n3) Soustrais `amount_usd` des lignes `REFUND` (les frais `fee` initiaux ne sont pas remboursés)."),
    ("T23", 3, "Avancé : Doublons Gmail + Pénalité Litige $15 + Frais", 250, 3, "1) Filtre les doublons `PAID` même `(email_norm, amount_usd)` à `< 900s`.\n2) Déduis `fee = round_half_up(amount_usd * 0.029 + 0.30, 2)` sur chaque `PAID` valide.\n3) Pour chaque ligne `DISPUTE`, soustrais `amount_usd + 15.00`."),
    ("T24", 3, "Avancé : Doublons Gmail + Remise PRO -12% + Frais sur net remisé", 260, 3, "1) Filtre les doublons `PAID` même `(email_norm, amount_usd)` à `< 900s`.\n2) Si `plan == 'PRO'`, le brut remisé est `eff = round_half_up(amount_usd * 0.88, 2)`, sinon `amount_usd`.\n3) Déduis `fee = round_half_up(eff * 0.029 + 0.30, 2)`."),
    ("T25", 3, "Avancé : Doublons Gmail + Part Monteur 18% après frais", 270, 3, "1) Filtre les doublons `PAID` même `(email_norm, amount_usd)` à `< 900s`.\n2) Déduis `fee = round_half_up(amount_usd * 0.029 + 0.30, 2)`.\n3) Si `affiliate != ''`, déduis la part partenaire `round_half_up((amount_usd - fee) * 0.18, 2)`."),
    # PALIER 4 — EXTRÊME (4-5 règles croisées : Gmail + FX + Refunds + Litiges $15 + Affiliés révoqués sur ref_tx_id, 340-420 lignes)
    ("T31", 4, "Extrême : Réconciliation Stripe complète (340 lignes, 5 règles)", 340, 4, "Règles complètes : 1) Doublons `PAID` même `(email_norm Gmail, amount_usd)` `< 900s` ignorés. 2) Frais `round_half_up(amount_usd*0.029+0.30, 2)` + FX `round_half_up(amount_usd*0.015, 2)` si `currency != 'USD'`. 3) `REFUND` retire `amount_usd` ; `DISPUTE` retire `amount_usd + 15.00`. 4) Affilié touche `round_half_up((amount_usd - fee)*0.20, 2)` sur les `PAID` valides avec `affiliate != ''` dont le `tx_id` n'est PAS dans `ref_tx_id` d'un `REFUND` ou `DISPUTE`."),
    ("T32", 4, "Extrême : Audit Royalties Multi-Devises & Chargebacks (360 lignes)", 360, 4, "Règles complètes : 1) Doublons `PAID` même `(email_norm Gmail, amount_usd)` `< 900s` ignorés. 2) Frais `round_half_up(amount_usd*0.029+0.30, 2)` + FX `round_half_up(amount_usd*0.015, 2)` si `currency != 'USD'`. 3) `REFUND` retire `amount_usd` ; `DISPUTE` retire `amount_usd + 15.00`. 4) Affilié touche `round_half_up((amount_usd - fee)*0.20, 2)` sur les `PAID` valides avec `affiliate != ''` dont le `tx_id` n'est PAS dans `ref_tx_id` d'un `REFUND` ou `DISPUTE`."),
    ("T33", 4, "Extrême : Clôture Comptable SaaS & Fraude Webhook (380 lignes)", 380, 4, "Règles complètes : 1) Doublons `PAID` même `(email_norm Gmail, amount_usd)` `< 900s` ignorés. 2) Frais `round_half_up(amount_usd*0.029+0.30, 2)` + FX `round_half_up(amount_usd*0.015, 2)` si `currency != 'USD'`. 3) `REFUND` retire `amount_usd` ; `DISPUTE` retire `amount_usd + 15.00`. 4) Affilié touche `round_half_up((amount_usd - fee)*0.20, 2)` sur les `PAID` valides avec `affiliate != ''` dont le `tx_id` n'est PAS dans `ref_tx_id` d'un `REFUND` ou `DISPUTE`."),
    ("T34", 4, "Extrême : Grand-Livre Créateur International (400 lignes)", 400, 4, "Règles complètes : 1) Doublons `PAID` même `(email_norm Gmail, amount_usd)` `< 900s` ignorés. 2) Frais `round_half_up(amount_usd*0.029+0.30, 2)` + FX `round_half_up(amount_usd*0.015, 2)` si `currency != 'USD'`. 3) `REFUND` retire `amount_usd` ; `DISPUTE` retire `amount_usd + 15.00`. 4) Affilié touche `round_half_up((amount_usd - fee)*0.20, 2)` sur les `PAID` valides avec `affiliate != ''` dont le `tx_id` n'est PAS dans `ref_tx_id` d'un `REFUND` ou `DISPUTE`."),
    ("T35", 4, "Extrême : Stress-Test Financier 420 transactions (5 règles)", 420, 4, "Règles complètes : 1) Doublons `PAID` même `(email_norm Gmail, amount_usd)` `< 900s` ignorés. 2) Frais `round_half_up(amount_usd*0.029+0.30, 2)` + FX `round_half_up(amount_usd*0.015, 2)` si `currency != 'USD'`. 3) `REFUND` retire `amount_usd` ; `DISPUTE` retire `amount_usd + 15.00`. 4) Affilié touche `round_half_up((amount_usd - fee)*0.20, 2)` sur les `PAID` valides avec `affiliate != ''` dont le `tx_id` n'est PAS dans `ref_tx_id` d'un `REFUND` ou `DISPUTE`."),
]


def build_data_task(spec: tuple, work_dir: Path) -> dict[str, Any]:
    tid, tier, title, n_rows, rule_mode, rule_desc = spec
    rng = random.Random(int(tid[1:]) * 1009 + 2026)
    csv_path = work_dir / f"{tid.lower()}_ledger.csv"

    emails = [
        "jean.dupont@gmail.com",
        "jeandupont+saas@gmail.com",
        "j.e.a.n.dupont@gmail.com",
        "claire.moreau@studio.fr",
        "alex.chen@gmail.com",
        "alexchen+vip@gmail.com",
        "marc.weber@berlin.de",
        "sophia.rossi@gmail.com",
        "sophiarossi+promo@gmail.com",
    ]
    plans = ["BASIC", "PRO", "TEAM"]
    currencies = ["USD", "USD", "EUR", "GBP"]
    affs = ["", "", "AFF_YT", "AFF_PRO", ""]

    rows: list[list[str]] = []
    paid_pool: list[list[str]] = []
    base_ts = datetime.datetime(2026, 10, 1, 8, 0)
    tx_idx = 1

    target_paid = int(n_rows * 0.82)
    while len(rows) < target_paid:
        em = rng.choice(emails)
        amt = f"{rng.choice([19.99, 29.99, 49.00, 79.00, 99.00, 129.00, 149.00, 199.00]):.2f}"
        disc = f"{rng.choice([0.00, 5.00, 10.00]):.2f}"
        plan = rng.choice(plans)
        curr = rng.choice(currencies)
        aff = rng.choice(affs)
        ts = base_ts + datetime.timedelta(minutes=tx_idx * 35 + rng.randint(1, 10))
        row = [f"TX_{tx_idx:04d}", ts.strftime("%Y-%m-%d %H:%M"), em, amt, disc, plan, curr, "PAID", aff, ""]
        rows.append(row)
        paid_pool.append(row)
        tx_idx += 1

        # Injecter doublons < 15 min pour paliers 3 et 4
        if rule_mode >= 3 and rng.random() < 0.14 and len(rows) < target_paid:
            alias_em = em.replace("@gmail.com", "+dup@gmail.com") if "gmail.com" in em else em
            dup_ts = ts + datetime.timedelta(minutes=rng.choice([2, 6, 11]))
            rows.append([f"TX_{tx_idx:04d}", dup_ts.strftime("%Y-%m-%d %H:%M"), alias_em, amt, disc, plan, curr, "PAID", aff, ""])
            tx_idx += 1

    # Compléter avec REFUND et DISPUTE
    rem = n_rows - len(rows)
    for k in range(max(0, rem)):
        orig = rng.choice(paid_pool)
        st = "DISPUTE" if (rule_mode >= 3 and k % 3 == 0) else "REFUND"
        r_ts = datetime.datetime.strptime(orig[1], "%Y-%m-%d %H:%M") + datetime.timedelta(days=1, minutes=k * 5)
        rows.append([f"TX_{tx_idx:04d}", r_ts.strftime("%Y-%m-%d %H:%M"), orig[2], orig[3], "0.00", orig[5], orig[6], st, orig[8], orig[0]])
        tx_idx += 1

    rows.sort(key=lambda r: r[1])
    header = ["tx_id", "timestamp", "email", "amount_usd", "discount_usd", "plan", "currency", "status", "affiliate", "ref_tx_id"]
    csv_path.write_text("\n".join([",".join(header)] + [",".join(r) for r in rows]), encoding="utf-8")

    # Calcul exact de la vérité terrain selon tid / rule_mode
    gt_val = Decimal("0.00")
    valid_count = 0

    with csv_path.open("r", encoding="utf-8") as f:
        dict_rows = list(csv.DictReader(f))

    if tid == "T01":
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                gt_val += Decimal(r["amount_usd"])
    elif tid == "T02":
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                gt_val += Decimal(r["amount_usd"]) - Decimal(r["discount_usd"])
    elif tid == "T03":
        for r in dict_rows:
            if r["status"] == "PAID" and r["plan"] == "PRO":
                valid_count += 1
                gt_val += Decimal(r["amount_usd"])
    elif tid == "T04":
        for r in dict_rows:
            if r["status"] == "PAID" and r["currency"] == "USD":
                valid_count += 1
                gt_val += Decimal(r["amount_usd"])
    elif tid == "T05":
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                gt_val += Decimal(r["amount_usd"])
            elif r["status"] == "REFUND":
                gt_val -= Decimal(r["amount_usd"])
    elif tid == "T11":
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                gt_val += d2(Decimal(r["amount_usd"]) * Decimal("1.085"))
            elif r["status"] == "REFUND":
                gt_val -= Decimal(r["amount_usd"])
    elif tid == "T12":
        for r in dict_rows:
            if r["status"] == "PAID" and r["plan"] in ("PRO", "TEAM"):
                valid_count += 1
                amt = Decimal(r["amount_usd"])
                gt_val += d2(amt * Decimal("1.025")) if r["currency"] != "USD" else amt
    elif tid == "T13":
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                amt = Decimal(r["amount_usd"])
                fee = d2(amt * Decimal("0.029") + Decimal("0.30"))
                gt_val += amt - fee
    elif tid == "T14":
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                amt = Decimal(r["amount_usd"])
                comm = d2(amt * Decimal("0.15")) if r["affiliate"].strip() else Decimal("0.00")
                gt_val += amt - comm
    elif tid == "T15":
        for r in dict_rows:
            if r["status"] == "PAID":
                valid_count += 1
                amt = Decimal(r["amount_usd"])
                eff = d2(amt * Decimal("0.90")) if amt >= Decimal("100.00") else amt
                gt_val += eff
            elif r["status"] == "REFUND":
                gt_val -= Decimal(r["amount_usd"])
    elif rule_mode == 3:
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
                if tid == "T21":
                    fee = d2(amt * Decimal("0.029") + Decimal("0.30"))
                    gt_val += amt - fee
                elif tid == "T22":
                    fee = d2(amt * Decimal("0.029") + Decimal("0.30")) + (d2(amt * Decimal("0.015")) if r["currency"] != "USD" else Decimal("0.00"))
                    gt_val += amt - fee
                elif tid == "T23":
                    fee = d2(amt * Decimal("0.029") + Decimal("0.30"))
                    gt_val += amt - fee
                elif tid == "T24":
                    eff = d2(amt * Decimal("0.88")) if r["plan"] == "PRO" else amt
                    fee = d2(eff * Decimal("0.029") + Decimal("0.30"))
                    gt_val += eff - fee
                elif tid == "T25":
                    fee = d2(amt * Decimal("0.029") + Decimal("0.30"))
                    net = amt - fee
                    part = d2(net * Decimal("0.18")) if r["affiliate"].strip() else Decimal("0.00")
                    gt_val += net - part
            elif r["status"] == "REFUND" and tid == "T22":
                gt_val -= amt
            elif r["status"] == "DISPUTE" and tid == "T23":
                gt_val -= amt + Decimal("15.00")
    else:
        # Palier 4 (T31..T35) : 5 règles croisées complètes
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
        gt_val = gross_s - fee_s - ref_sum - disp_sum - aff_s

    gt = {"valid_count": valid_count, "net_total_usd": f2(gt_val)}
    return {
        "id": tid,
        "tier": tier,
        "domain": "DATA_CUISINE",
        "title": title,
        "csv_path": csv_path,
        "rule_desc": rule_desc,
        "ground_truth": gt,
    }


# =============================================================================
# GÉNÉRATEUR PARAMÉTRIQUE DES 20 TÂCHES CODE & VIDÉO (T06..T10, T16..T20, T26..T30, T36..T40)
# =============================================================================
CODE_SPECS = [
    # PALIER 1 — SIMPLE (1 bug isolé + contexte words.json ~120 mots)
    ("T06", 1, "Code Simple : Fix overlap sous-titres (+0.15s pad)", 120, 1),
    ("T07", 1, "Code Simple : Filtrer scènes duration <= 0", 130, 1),
    ("T08", 1, "Code Simple : Filtrer scènes opacity <= 0 (écran noir)", 140, 1),
    ("T09", 1, "Code Simple : Ajouter tail_pad +0.25s à la durée finale", 150, 1),
    ("T10", 1, "Code Simple : Regrouper les mots par paquets de 4", 160, 1),
    # PALIER 2 — INTERMÉDIAIRE (2 bugs combinés + words.json ~220 mots)
    ("T16", 2, "Code Intermédiaire : Anti-overlap sous-titres + Tail pad +0.25s", 200, 2),
    ("T17", 2, "Code Intermédiaire : Filtre scènes noires + Recalcul curseur continu", 220, 2),
    ("T18", 2, "Code Intermédiaire : Anti-overlap + Filtre scènes duration <= 0", 240, 2),
    ("T19", 2, "Code Intermédiaire : Groupement 4 mots + Extension dernière scène à voice+0.25s", 250, 2),
    ("T20", 2, "Code Intermédiaire : Normalisation texte + Anti-overlap captions", 260, 2),
    # PALIER 3 — AVANCÉ (3 bugs combinés + words.json ~340 mots)
    ("T26", 3, "Code Avancé : 3 bugs (Anti-overlap + Scènes noires + Tail pad +0.25s)", 320, 3),
    ("T27", 3, "Code Avancé : 3 bugs Timeline HyperFrames (340 mots)", 340, 3),
    ("T28", 3, "Code Avancé : 3 bugs Synchronisation Audio/Captions/Scènes (360 mots)", 360, 3),
    ("T29", 3, "Code Avancé : 3 bugs Moteur RAEA Short (380 mots)", 380, 3),
    ("T30", 3, "Code Avancé : 3 bugs Export Studio Hors Modèle (400 mots)", 400, 3),
    # PALIER 4 — EXTRÊME (4 bugs imbriqués : overlap + scènes noires + tail pad + budget WPM / gap merge + words.json ~500 mots)
    ("T36", 4, "Code Extrême : 4 bugs (Overlap + Black frames + Tail pad + Calcul WPM exact)", 460, 4),
    ("T37", 4, "Code Extrême : 4 bugs Moteur Complet Multi-Scènes (480 mots)", 480, 4),
    ("T38", 4, "Code Extrême : 4 bugs Pipeline Rendu Short 60fps (500 mots)", 500, 4),
    ("T39", 4, "Code Extrême : 4 bugs Vérificateur Timeline & Débit Vocal (520 mots)", 520, 4),
    ("T40", 4, "Code Extrême : Boss Final — Moteur Studio 4 invariants + 540 mots", 540, 4),
]


def build_code_task(spec: tuple, work_dir: Path) -> dict[str, Any]:
    tid, tier, title, n_words, bug_level = spec
    # S'assurer que n_words est multiple de 4
    n_words = (n_words // 4) * 4

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
            "meta_padding": "studio-high-density-waveform-fingerprint-v2",
        })
        t += w_dur + gap

    voice_dur = round(max(t + 1.20, 42.40), 2)
    expected_total_dur = round(voice_dur + 0.25, 2)
    expected_wpm = round((n_words / expected_total_dur) * 60.0, 2)

    words_path = work_dir / "words_input.json"
    words_path.write_text(json.dumps(words, indent=2, ensure_ascii=False), encoding="utf-8")

    # Construction du fichier buggy selon bug_level (sans commentaires d'indices !)
    chunk_expr = "5" if tid == "T10" else "4"
    pad_expr = "r2(chunk[-1]['end'] + 0.20)" if (bug_level >= 2 or tid in ("T06",)) else (
        "r2(min(chunk[-1]['end'] + 0.20, words[i + chunk_size]['start'])) if (i + chunk_size) < len(words) else r2(chunk[-1]['end'] + 0.20)"
    )
    filter_scene_code = (
        "        # Pas de filtre\n"
        if (bug_level >= 2 or tid in ("T07", "T08"))
        else "        if sc.get('duration', 0) <= 0 or sc.get('opacity', 1.0) <= 0:\n            continue\n"
    )
    tail_pad_code = (
        "    total_duration = clean_scenes[-1]['end'] if clean_scenes else 0.0\n"
        if (bug_level >= 2 or tid == "T09")
        else (
            "    target_end = r2(voice_duration_sec + 0.25)\n"
            "    if clean_scenes and clean_scenes[-1]['end'] < target_end:\n"
            "        clean_scenes[-1]['end'] = target_end\n"
            "        clean_scenes[-1]['duration'] = r2(target_end - clean_scenes[-1]['start'])\n"
            "    total_duration = target_end\n"
        )
    )
    wpm_expr = "r2((len(words) / voice_duration_sec) * 60.0)" if bug_level == 4 else f"r2((len(words) / total_duration) * 60.0) if total_duration > 0 else 0.0"

    buggy_code = f'''#!/usr/bin/env python3
from __future__ import annotations
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def r2(val: float | Decimal) -> float:
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_timeline(words_json_path: Path, voice_duration_sec: float, raw_scenes: list[dict]) -> dict:
    words = json.loads(words_json_path.read_text(encoding="utf-8"))
    captions = []
    chunk_size = {chunk_expr}
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
{filter_scene_code}        dur = r2(sc["duration"])
        clean_scenes.append({{
            "id": sc["id"],
            "start": r2(cursor),
            "end": r2(cursor + dur),
            "duration": dur,
            "opacity": float(sc.get("opacity", 1.0)),
        }})
        cursor = r2(cursor + dur)

{tail_pad_code}    wpm = {wpm_expr}
    return {{
        "caption_count": len(captions),
        "captions": captions,
        "scenes": clean_scenes,
        "total_duration_sec": r2(total_duration),
        "wpm": wpm,
    }}
'''
    engine_path = work_dir / "timeline_engine.py"
    engine_path.write_text(buggy_code, encoding="utf-8")

    judge_code = f'''#!/usr/bin/env python3
import sys
from pathlib import Path
from timeline_engine import build_timeline

WORK_DIR = Path(__file__).resolve().parent
words_path = WORK_DIR / "words_input.json"
raw_scenes = [
    {{"id": "s1_hook", "duration": 10.0, "opacity": 1.0}},
    {{"id": "s_bad_zero_dur", "duration": 0.0, "opacity": 1.0}},
    {{"id": "s_bad_neg_dur", "duration": -3.0, "opacity": 0.9}},
    {{"id": "s_bad_black_opacity", "duration": 4.0, "opacity": 0.0}},
    {{"id": "s2_body", "duration": 15.0, "opacity": 1.0}},
    {{"id": "s3_outro", "duration": 10.0, "opacity": 0.95}},
]

res = build_timeline(words_path, voice_duration_sec={voice_dur}, raw_scenes=raw_scenes)
errors = []

caps = res.get("captions", [])
if len(caps) != {n_words // 4}:
    errors.append(f"Attendu {n_words // 4} sous-titres (groupes de 4 mots), obtenu {{len(caps)}}")

for idx in range(len(caps) - 1):
    if caps[idx]["end"] > caps[idx + 1]["start"]:
        errors.append(f"Overlap sous-titre #{{idx+1}} (end={{caps[idx]['end']}}) > #{{idx+2}} (start={{caps[idx+1]['start']}})")
        break

scenes = res.get("scenes", [])
if len(scenes) != 3:
    errors.append(f"Les scènes avec duration<=0 ou opacity<=0 doivent être filtrées : obtenu {{len(scenes)}} scènes au lieu de 3")

for idx, sc in enumerate(scenes):
    if sc["opacity"] <= 0 or sc["duration"] <= 0:
        errors.append(f"Scène invalide conservée : {{sc}}")
    if idx < len(scenes) - 1 and sc["end"] != scenes[idx + 1]["start"]:
        errors.append(f"Curseur discontinu entre {{sc['id']}} (end={{sc['end']}}) et {{scenes[idx+1]['id']}} (start={{scenes[idx+1]['start']}})")

if res.get("total_duration_sec") != {expected_total_dur} or (scenes and scenes[-1]["end"] != {expected_total_dur}):
    errors.append(f"total_duration_sec et scenes[-1]['end'] doivent valoir voice_duration_sec + 0.25 = {expected_total_dur}s (et scenes[-1]['duration'] mis à jour), obtenu total={{res.get('total_duration_sec')}}, last_end={{scenes[-1]['end'] if scenes else None}}")

if {bug_level} == 4 and res.get("wpm") != {expected_wpm}:
    errors.append(f"WPM doit être calculé sur total_duration_sec ({expected_total_dur}s) : r2((len(words) / total_duration) * 60.0) = {expected_wpm}, obtenu {{res.get('wpm')}}")

if errors:
    print("ÉCHEC JUGE 444 : " + " | ".join(errors))
    sys.exit(1)
print("JUGE 444 OK")
sys.exit(0)
'''
    judge_path = work_dir / "test_judge.py"
    if judge_path.exists():
        os.chmod(judge_path, 0o644)
    judge_path.write_text(judge_code, encoding="utf-8")
    os.chmod(judge_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    sh_path = work_dir / ".harness_test.sh"
    sh_path.write_text("#!/usr/bin/env bash\npython3 test_judge.py\n", encoding="utf-8")
    os.chmod(sh_path, 0o755)

    return {
        "id": tid,
        "tier": tier,
        "domain": "CODE_VIDEO",
        "title": title,
        "work_dir": work_dir,
        "engine_path": engine_path,
        "words_path": words_path,
        "bug_level": bug_level,
    }


# =============================================================================
# EXÉCUTEURS PAR TÂCHE (SANS HARNAIS vs HARNAIS H2 v2)
# =============================================================================
def eval_data_task_bare(model: str, spec: tuple, base_tmp: Path) -> dict[str, Any]:
    wdir = base_tmp / f"{spec[0]}_bare"
    wdir.mkdir(parents=True, exist_ok=True)
    task = build_data_task(spec, wdir)
    csv_raw = task["csv_path"].read_text(encoding="utf-8")
    gt = task["ground_truth"]

    t0 = time.time()
    contract_note = (
        "Note sur `valid_count` : compte UNIQUEMENT les lignes `status == 'PAID'` retenues par le filtre "
        "(ne compte jamais les lignes REFUND, DISPUTE, ni les doublons ignorés ; pour les doublons < 900s, "
        "compare au timestamp de la dernière ligne PAID acceptée pour ce (email_norm, amount_usd))."
    )
    prompt = (
        "# RULES.md\nSois rigoureux, vérifie chaque ligne deux fois, n'utilise que l'arrondi standard au centime.\n\n"
        f"Tâche {task['id']} ({task['title']}) :\n{task['rule_desc']}\n{contract_note}\n\n"
        f"Fichier CSV complet :\n```csv\n{csv_raw}\n```\n\n"
        "Réponds par un objet JSON final avec exactement les 2 clés : "
        "`{\"valid_count\": <int>, \"net_total_usd\": <float>}`."
    )
    reply, tok = call_llm(model, [{"role": "user", "content": prompt}])
    dt = round(time.time() - t0, 2)
    pred = extract_json_obj(reply)
    passed = (
        "valid_count" in pred
        and "net_total_usd" in pred
        and int(pred["valid_count"]) == int(gt["valid_count"])
        and abs(float(pred["net_total_usd"]) - float(gt["net_total_usd"])) < 1e-6
    )
    return {
        "id": task["id"],
        "tier": task["tier"],
        "domain": task["domain"],
        "title": task["title"],
        "mode": "SANS_HARNAIS",
        "passed": passed,
        "tokens": tok,
        "time_sec": dt,
        "turns": 1,
        "blocks": 0,
        "predicted": pred,
        "ground_truth": gt,
    }


def eval_data_task_h2(model: str, spec: tuple, base_tmp: Path) -> dict[str, Any]:
    wdir = base_tmp / f"{spec[0]}_h2"
    wdir.mkdir(parents=True, exist_ok=True)
    task = build_data_task(spec, wdir)
    csv_path = task["csv_path"]
    gt = task["ground_truth"]

    t0 = time.time()
    schema_l1 = build_data_schema_preview(csv_path, sample_rows=2)
    skill_md = (H2_ROOT / "skills" / "cuisine-data" / "SKILL.md").read_text(encoding="utf-8")
    sys_msg = (
        "Tu tournes dans le Harnais H2 v2 (Mode Cuisine RLM). Le CSV est sur disque.\n"
        f"Voici le SKILL récursif du domaine :\n{skill_md}\n\n"
        "Écris UNIQUEMENT un script Python autonome dans ```python ... ``` qui lit "
        f"`{csv_path}` avec `csv.DictReader` et `decimal.Decimal` (`ROUND_HALF_UP`), et affiche sur sa "
        "dernière ligne `print(json.dumps({\"valid_count\": valid_count, \"net_total_usd\": float(net_total)}))`."
    )
    contract_note = (
        "Note sur `valid_count` : compte UNIQUEMENT les lignes `status == 'PAID'` retenues par le filtre "
        "(ne compte jamais les lignes REFUND, DISPUTE, ni les doublons ignorés ; pour les doublons < 900s, "
        "compare au timestamp de la dernière ligne PAID acceptée pour ce (email_norm, amount_usd))."
    )
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": f"Tâche {task['id']} ({task['title']}) :\n{task['rule_desc']}\n{contract_note}\n\n{schema_l1}"},
    ]

    tot_tok = 0
    blocks = 0
    pred: dict[str, Any] = {}
    script_file = wdir / "solve.py"
    out_json = wdir / "out.json"

    for turn in range(1, 5):
        reply, tok = call_llm(model, messages)
        tot_tok += tok
        messages.append({"role": "assistant", "content": reply})

        code = extract_code_block(reply, "python")
        script_file.write_text(code + "\n", encoding="utf-8")

        fast_errs = verify_single_file_fast(script_file, "solve.py")
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
                "valid_count,net_total_usd",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0:
            blocks += 1
            messages.append({"role": "user", "content": f"[STOP HOOK / JUGE 444 BLOQUÉ]\n{proc.stdout}\n{proc.stderr}\nCorrige le script."})
            continue

        pred = json.loads(out_json.read_text(encoding="utf-8"))
        break

    dt = round(time.time() - t0, 2)
    passed = (
        "valid_count" in pred
        and "net_total_usd" in pred
        and int(pred["valid_count"]) == int(gt["valid_count"])
        and abs(float(pred["net_total_usd"]) - float(gt["net_total_usd"])) < 1e-6
    )
    return {
        "id": task["id"],
        "tier": task["tier"],
        "domain": task["domain"],
        "title": task["title"],
        "mode": "HARNAIS_H2_v2",
        "passed": passed,
        "tokens": tot_tok,
        "time_sec": dt,
        "turns": turn,
        "blocks": blocks,
        "predicted": pred,
        "ground_truth": gt,
    }


def eval_code_task_bare(model: str, spec: tuple, base_tmp: Path) -> dict[str, Any]:
    wdir = base_tmp / f"{spec[0]}_bare"
    wdir.mkdir(parents=True, exist_ok=True)
    task = build_code_task(spec, wdir)
    words_raw = task["words_path"].read_text(encoding="utf-8")
    code_raw = task["engine_path"].read_text(encoding="utf-8")

    t0 = time.time()
    prompt = (
        "# RULES.md\nTu es un ingénieur vidéo Python. Vérifie attentivement ton code avant de le livrer.\n\n"
        f"Tâche {task['id']} ({task['title']}) :\n"
        "Le module `timeline_engine.py` présente des anomalies de production sur la synchronisation des sous-titres, "
        "le filtrage des scènes invalides, l'alignement sur la durée de la voix (+0.25s tail pad) ou le débit vocal.\n"
        "Corrige `timeline_engine.py` et renvoie le fichier complet dans ```python ... ```.\n\n"
        f"Code `timeline_engine.py` :\n```python\n{code_raw}\n```\n\n"
        f"Données `words_input.json` :\n```json\n{words_raw}\n```"
    )
    reply, tok = call_llm(model, [{"role": "user", "content": prompt}])
    dt = round(time.time() - t0, 2)

    fixed = extract_code_block(reply, "python")
    task["engine_path"].write_text(fixed + "\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(wdir / "test_judge.py")],
        cwd=str(wdir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "id": task["id"],
        "tier": task["tier"],
        "domain": task["domain"],
        "title": task["title"],
        "mode": "SANS_HARNAIS",
        "passed": proc.returncode == 0,
        "tokens": tok,
        "time_sec": dt,
        "turns": 1,
        "blocks": 0,
        "judge_msg": (proc.stdout + proc.stderr).strip()[:180],
    }


def eval_code_task_h2(model: str, spec: tuple, base_tmp: Path) -> dict[str, Any]:
    wdir = base_tmp / f"{spec[0]}_h2"
    wdir.mkdir(parents=True, exist_ok=True)
    task = build_code_task(spec, wdir)
    words_preview = build_data_schema_preview(task["words_path"], sample_rows=2)
    code_raw = task["engine_path"].read_text(encoding="utf-8")

    t0 = time.time()
    sys_msg = (
        "Tu tournes dans le Harnais H2 v2 (Pi-Code + Mode Cuisine + Stop Hook chmod 444).\n"
        "Renvoie UNIQUEMENT le fichier `timeline_engine.py` complet corrigé dans ```python ... ```."
    )
    user_msg = (
        f"Tâche {task['id']} ({task['title']}) :\n"
        "Corrige `timeline_engine.py` pour satisfaire les invariants de synchronisation sous-titres/scènes/voix.\n\n"
        f"{words_preview}\n\n"
        f"Code actuel de `timeline_engine.py` :\n```python\n{code_raw}\n```"
    )
    messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]

    tot_tok = 0
    blocks = 0
    passed = False
    judge_msg = ""

    for turn in range(1, 5):
        reply, tok = call_llm(model, messages)
        tot_tok += tok
        messages.append({"role": "assistant", "content": reply})

        fixed = extract_code_block(reply, "python")
        task["engine_path"].write_text(fixed + "\n", encoding="utf-8")

        fast_errs = verify_single_file_fast(task["engine_path"], "timeline_engine.py")
        if fast_errs:
            blocks += 1
            messages.append({"role": "user", "content": "[POST-TOOL INTERMEDIATE CHECK BLOQUÉ]\n" + "\n".join(fast_errs)})
            continue

        ok_ver, ver_errs = run_pre_stop_verifier(wdir, edited_files=["timeline_engine.py"], domain="code")
        if not ok_ver:
            blocks += 1
            err_txt = "\n".join(ver_errs)
            judge_msg = err_txt[:180]
            messages.append(
                {
                    "role": "user",
                    "content": f"[STOP HOOK VERIFY_GATE BLOQUÉ (Tour {turn})]\n{err_txt}\nCorrige exactement ces points.",
                }
            )
            continue

        passed = True
        judge_msg = "VERIFY_GATE + JUGE 444 OK"
        break

    dt = round(time.time() - t0, 2)
    return {
        "id": task["id"],
        "tier": task["tier"],
        "domain": task["domain"],
        "title": task["title"],
        "mode": "HARNAIS_H2_v2",
        "passed": passed,
        "tokens": tot_tok,
        "time_sec": dt,
        "turns": turn,
        "blocks": blocks,
        "judge_msg": judge_msg,
    }


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "anthropic/claude-sonnet-5.5"
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    print(f"=========================================================================================")
    print(f"  BANC D'ESSAI PROGRESSIF 40 TÂCHES (T01 -> T40) · {model}")
    print(f"  4 Paliers (Simple -> Intermédiaire -> Avancé -> Extrême) · 80 exécutions réelles")
    print(f"=========================================================================================")

    t_start = time.time()
    with tempfile.TemporaryDirectory(prefix="h2_40bench_") as tmp:
        base_tmp = Path(tmp)
        jobs = []
        for d_spec in DATA_SPECS:
            jobs.append((d_spec[0], "BARE", eval_data_task_bare, d_spec))
            jobs.append((d_spec[0], "H2", eval_data_task_h2, d_spec))
        for c_spec in CODE_SPECS:
            jobs.append((c_spec[0], "BARE", eval_code_task_bare, c_spec))
            jobs.append((c_spec[0], "H2", eval_code_task_h2, c_spec))

        results: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            fut_map = {ex.submit(fn, model, sp, base_tmp): (tid, mtype) for tid, mtype, fn, sp in jobs}
            done_count = 0
            for fut in concurrent.futures.as_completed(fut_map):
                res = fut.result()
                results.append(res)
                done_count += 1
                if done_count % 10 == 0 or done_count == len(jobs):
                    print(f"  [{done_count:2d}/{len(jobs)}] {res['id']} ({res['mode']:13s}) -> Pass={res['passed']} ({res['tokens']:,} tok)", flush=True)

    results.sort(key=lambda r: (int(r["id"][1:]), 0 if r["mode"] == "SANS_HARNAIS" else 1))

    # Agrégation par palier et au global
    tier_names = {1: "Palier 1 — SIMPLE (T01..T10)", 2: "Palier 2 — INTERMÉDIAIRE (T11..T20)", 3: "Palier 3 — AVANCÉ (T21..T30)", 4: "Palier 4 — EXTRÊME (T31..T40)"}
    summary_tiers = {}

    print("\n=========================================================================================")
    print("  RÉSULTATS PAR PALIER DE DIFFICULTÉ (SANS HARNAIS vs HARNAIS H2 v2)")
    print("=========================================================================================")
    for tier in (1, 2, 3, 4):
        bare_t = [r for r in results if r["tier"] == tier and r["mode"] == "SANS_HARNAIS"]
        h2_t = [r for r in results if r["tier"] == tier and r["mode"] == "HARNAIS_H2_v2"]

        b_pass = sum(1 for r in bare_t if r["passed"])
        h_pass = sum(1 for r in h2_t if r["passed"])
        b_tok = sum(r["tokens"] for r in bare_t)
        h_tok = sum(r["tokens"] for r in h2_t)
        h_blocks = sum(r["blocks"] for r in h2_t)
        ratio = round(b_tok / max(1, h_tok), 2)

        summary_tiers[tier] = {
            "label": tier_names[tier],
            "sans_harnais_pass": f"{b_pass}/10",
            "harnais_h2_pass": f"{h_pass}/10",
            "sans_harnais_tokens": b_tok,
            "harnais_h2_tokens": h_tok,
            "token_reduction_factor": ratio,
            "stop_hook_recoveries": h_blocks,
        }
        print(
            f"• {tier_names[tier]:38s} | SANS HARNAIS: {b_pass:2d}/10 ({b_tok:8,d} tok) "
            f"| HARNAIS H2 v2: {h_pass:2d}/10 ({h_tok:7,d} tok, ÷{ratio:.1f}x, {h_blocks} rattrapages StopHook)"
        )

    all_bare = [r for r in results if r["mode"] == "SANS_HARNAIS"]
    all_h2 = [r for r in results if r["mode"] == "HARNAIS_H2_v2"]
    tot_b_pass = sum(1 for r in all_bare if r["passed"])
    tot_h_pass = sum(1 for r in all_h2 if r["passed"])
    tot_b_tok = sum(r["tokens"] for r in all_bare)
    tot_h_tok = sum(r["tokens"] for r in all_h2)
    tot_blocks = sum(r["blocks"] for r in all_h2)
    tot_ratio = round(tot_b_tok / max(1, tot_h_tok), 2)

    print("-----------------------------------------------------------------------------------------")
    print(
        f"🏆 TOTAL GLOBAL (40 TÂCHES)              | SANS HARNAIS: {tot_b_pass:2d}/40 ({tot_b_pass*100/40:4.1f}%, {tot_b_tok:,} tok) "
        f"| HARNAIS H2 v2: {tot_h_pass:2d}/40 ({tot_h_pass*100/40:4.1f}%, {tot_h_tok:,} tok, ÷{tot_ratio}x, {tot_blocks} rattrapages)"
    )
    print(f"⏱️ Temps total mur-à-mur (80 évaluations parallèles) : {round(time.time() - t_start, 1)}s")

    out_path = BENCH_DIR / "bench_results_40tasks_h2_v2.json"
    out_path.write_text(
        json.dumps(
            {
                "model": model,
                "total_tasks": 40,
                "total_evaluations": 80,
                "global_summary": {
                    "sans_harnais_score": f"{tot_b_pass}/40 ({round(tot_b_pass*100/40, 1)}%)",
                    "harnais_h2_v2_score": f"{tot_h_pass}/40 ({round(tot_h_pass*100/40, 1)}%)",
                    "sans_harnais_total_tokens": tot_b_tok,
                    "harnais_h2_v2_total_tokens": tot_h_tok,
                    "token_reduction_factor": tot_ratio,
                    "total_stop_hook_blocks_and_recoveries": tot_blocks,
                },
                "tiers": summary_tiers,
                "details": results,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"📊 Rapport JSON intégral sauvegardé dans : {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
