#!/usr/bin/env python3
"""
Banc d'Essai Officiel — Harnais H2 v2 (2 Tâches Différentes : Data Mode Cuisine vs Code & Timeline Vidéo)
Compare sur de vrais appels modèles :
  - Condition A : SANS HARNAIS (Prompt RULES.md seul, fichier injecté en contexte L1, pas de Stop Hook)
  - Condition B : AVEC HARNAIS H2 v2 (Mode Cuisine L1 ~120 tok + Exécution Python L2 + AST Mode 4 +
                  Vérification intermédiaire + Stop Hook & Juges chmod 444 avec auto-correction)

Tâche 1 (DATA / FINANCE / MODE CUISINE) : `T1_STRIPE_RECONCILIATION`
  - 180 transactions Stripe SaaS multi-devises avec 4 pièges :
    1) Doublons de webhook (< 15 min, même email Gmail normalisé sans '.' ni '+tag' et même gross_usd)
    2) Frais Stripe 2.9% + $0.30 par transaction valide (arrondi ROUND_HALF_UP ligne par ligne) + 1.5% si devise != USD
    3) REFUND : rembourse le montant brut mais Stripe garde ses frais initiaux ; DISPUTE_LOST : retire brut + $15.00 de pénalité
    4) Affilié : 20% du net après frais Stripe sur les transactions SUCCEEDED non remboursées/disputées avec code affilié

Tâche 2 (CODE / AUDIO-VIDEO TIMELINE BUGFIX) : `T2_TIMELINE_SYNC_BUGFIX`
  - Un moteur Python `timeline_engine.py` + `words.json` (320 mots horodatés en Mode Cuisine) avec 3 bugs de prod :
    1) Chevauchement (overlap) entre sous-titres consécutifs (`prev.end > curr.start`)
    2) Coupure prématurée de la dernière scène avant `voice_duration + 0.25s`
    3) Scènes invalides (`opacity <= 0` ou `duration <= 0`) non filtrées/corrigées
  - Validé par un juge unitaire verrouillé en `chmod 444` (`test_timeline_judge.py` via `.harness_test.sh`).
"""
from __future__ import annotations

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

BENCH_DIR = Path(__file__).resolve().parent
H2_ROOT = BENCH_DIR.parent
sys.path.insert(0, str(H2_ROOT / "core"))

from context_mgr import build_data_schema_preview  # noqa: E402
from verify import check_ast_anti_hardcoding, run_pre_stop_verifier, verify_single_file_fast  # noqa: E402


def d2(val: object) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_gmail(email: str) -> str:
    email = email.strip().lower()
    local, _, domain = email.partition("@")
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+")[0].replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


# =============================================================================
# 1. GÉNÉRATION DE LA TÂCHE 1 : DATA / STRIPE RECONCILIATION (180 lignes CSV)
# =============================================================================
def setup_task1_data(work_dir: Path) -> tuple[Path, dict[str, float | int]]:
    rng = random.Random(20261124)
    csv_path = work_dir / "t1_stripe_payouts.csv"

    customers = [
        "alex.martin@gmail.com",
        "alexmartin+promo@gmail.com",
        "a.l.e.x.martin@gmail.com",
        "sarah.connor@cyberdyne.io",
        "jean.dupont@gmail.com",
        "jeandupont+yt@gmail.com",
        "marie.curie@sorbonne.fr",
        "lucas.dev+saas@gmail.com",
        "lucasdev@gmail.com",
        "emma.watson@studio.co.uk",
    ]
    plans = [("99.00", "USD"), ("49.00", "USD"), ("149.00", "EUR"), ("29.99", "USD"), ("199.00", "GBP")]
    affiliates = ["", "", "", "YT_JEFF", "PARTNER_AI", ""]

    rows: list[list[str]] = []
    base_ts = datetime.datetime(2026, 11, 1, 8, 0)
    tx_num = 1

    succeeded_records: list[list[str]] = []
    for i in range(145):
        cust = rng.choice(customers)
        amt, curr = rng.choice(plans)
        aff = rng.choice(affiliates)
        ts = base_ts + datetime.timedelta(hours=i * 2, minutes=rng.randint(1, 40))
        row = [f"STX_{tx_num:04d}", ts.strftime("%Y-%m-%d %H:%M"), cust, amt, curr, "SUCCEEDED", aff, ""]
        rows.append(row)
        succeeded_records.append(row)
        tx_num += 1

        # Injecter 15 doublons de webhook (< 15 minutes d'écart, même client Gmail sous alias différent !)
        if i in (5, 14, 23, 31, 42, 55, 63, 74, 88, 95, 104, 112, 121, 133, 140):
            alias_cust = cust.replace("@gmail.com", "+retry@gmail.com") if "gmail.com" in cust else cust
            dup_ts = ts + datetime.timedelta(minutes=rng.choice([2, 5, 9, 12]))
            dup_row = [f"STX_{tx_num:04d}", dup_ts.strftime("%Y-%m-%d %H:%M"), alias_cust, amt, curr, "SUCCEEDED", aff, ""]
            rows.append(dup_row)
            tx_num += 1

    # Injecter 12 REFUND et 8 DISPUTE_LOST liés à de vraies transactions SUCCEEDED
    sampled = rng.sample(succeeded_records, 20)
    for idx, orig in enumerate(sampled):
        ev_type = "REFUND" if idx < 12 else "DISPUTE_LOST"
        ev_ts = datetime.datetime.strptime(orig[1], "%Y-%m-%d %H:%M") + datetime.timedelta(days=1, hours=3)
        rows.append([f"STX_{tx_num:04d}", ev_ts.strftime("%Y-%m-%d %H:%M"), orig[2], orig[3], orig[4], ev_type, orig[6], orig[0]])
        tx_num += 1

    rows.sort(key=lambda r: r[1])
    header = ["tx_id", "timestamp", "customer_email", "gross_usd", "currency", "event_type", "affiliate_code", "ref_tx_id"]
    csv_text = "\n".join([",".join(header)] + [",".join(r) for r in rows])
    csv_path.write_text(csv_text, encoding="utf-8")

    # Calcul Ground Truth déterministe au centime près
    gt = compute_task1_ground_truth(csv_path)
    return csv_path, gt


def compute_task1_ground_truth(csv_path: Path) -> dict[str, float | int]:
    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    last_seen: dict[tuple[str, str], datetime.datetime] = {}
    valid_succeeded: dict[str, dict[str, object]] = {}
    reversed_tx_ids: set[str] = set()
    refund_gross_total = Decimal("0.00")
    dispute_Loss_total = Decimal("0.00")

    for r in rows:
        etype = r["event_type"]
        ts = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M")
        amt = Decimal(r["gross_usd"])
        norm_email = normalize_gmail(r["customer_email"])

        if etype == "SUCCEEDED":
            key = (norm_email, r["gross_usd"])
            if key in last_seen and (ts - last_seen[key]).total_seconds() < 900:
                last_seen[key] = ts
                continue
            last_seen[key] = ts
            base_fee = d2(amt * Decimal("0.029") + Decimal("0.30"))
            fx_fee = d2(amt * Decimal("0.015")) if r["currency"] != "USD" else Decimal("0.00")
            fee = base_fee + fx_fee
            valid_succeeded[r["tx_id"]] = {
                "gross": amt,
                "fee": fee,
                "net": amt - fee,
                "affiliate": r["affiliate_code"].strip(),
            }
        elif etype == "REFUND":
            ref_id = r["ref_tx_id"].strip()
            reversed_tx_ids.add(ref_id)
            refund_gross_total += amt
        elif etype == "DISPUTE_LOST":
            ref_id = r["ref_tx_id"].strip()
            reversed_tx_ids.add(ref_id)
            dispute_Loss_total += amt + Decimal("15.00")

    valid_tx_count = len(valid_succeeded)
    gross_succeeded = sum((v["gross"] for v in valid_succeeded.values()), Decimal("0.00"))
    stripe_fees_total = sum((v["fee"] for v in valid_succeeded.values()), Decimal("0.00"))

    affiliate_payout = Decimal("0.00")
    for tx_id, info in valid_succeeded.items():
        if info["affiliate"] and tx_id not in reversed_tx_ids:
            affiliate_payout += d2(Decimal(str(info["net"])) * Decimal("0.20"))

    final_net_payout = gross_succeeded - stripe_fees_total - refund_gross_total - dispute_Loss_total - affiliate_payout
    return {
        "valid_tx_count": valid_tx_count,
        "stripe_fees_total_usd": float(d2(stripe_fees_total)),
        "affiliate_payout_usd": float(d2(affiliate_payout)),
        "final_net_payout_usd": float(d2(final_net_payout)),
    }


# =============================================================================
# 2. GÉNÉRATION DE LA TÂCHE 2 : CODE / VIDEO TIMELINE ENGINE + JUGE CHMOD 444
# =============================================================================
BUGGY_TIMELINE_ENGINE = '''#!/usr/bin/env python3
"""
timeline_engine.py — Moteur de synchronisation Audio / Sous-titres / Scènes pour Shorts Vidéo.
Contient 3 bugs de production que l'agent doit diagnostiquer et réparer.
"""
from __future__ import annotations
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def r2(val: float | Decimal) -> float:
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_timeline_from_words(words_json_path: Path, voice_duration_sec: float, raw_scenes: list[dict]) -> dict:
    words = json.loads(words_json_path.read_text(encoding="utf-8"))

    # 1. Construction des sous-titres par groupes de 4 mots
    captions = []
    chunk_size = 4
    for i in range(0, len(words), chunk_size):
        chunk = words[i : i + chunk_size]
        if not chunk:
            continue
        start_t = r2(chunk[0]["start"])
        # BUG 1 : ajoute un padding de +0.18s sur `end` sans borner par le `start` du groupe suivant,
        # ce qui crée des chevauchements (overlaps : prev["end"] > next["start"]) !
        end_t = r2(chunk[-1]["end"] + 0.18)
        captions.append({
            "index": len(captions) + 1,
            "text": " ".join(w["word"] for w in chunk),
            "start": start_t,
            "end": end_t,
        })

    # 2. Filtrage et normalisation des scènes visuelles
    # BUG 2 : ne filtre pas les scènes corrompues (opacity <= 0 ou duration <= 0) -> écran noir !
    clean_scenes = []
    cursor = 0.0
    for sc in raw_scenes:
        dur = r2(sc["duration"])
        clean_scenes.append({
            "id": sc["id"],
            "start": r2(cursor),
            "end": r2(cursor + dur),
            "duration": dur,
            "opacity": float(sc.get("opacity", 1.0)),
        })
        cursor = r2(cursor + dur)

    # 3. Alignement de la dernière scène sur la durée de la voix + 0.25s de tail pad
    # BUG 3 : oublie d'étendre `clean_scenes[-1]["end"]` et `duration` jusqu'à `r2(voice_duration_sec + 0.25)` !
    total_duration = clean_scenes[-1]["end"] if clean_scenes else 0.0

    return {
        "caption_count": len(captions),
        "captions": captions,
        "scenes": clean_scenes,
        "total_duration_sec": r2(total_duration),
    }
'''

JUDGE_TIMELINE_TEST = '''#!/usr/bin/env python3
"""
test_timeline_judge.py — Juge unitaire immuable (chmod 444) pour la Tâche 2.
Vérifie les 4 invariants du moteur de timeline vidéo :
  1. Zéro chevauchement entre deux sous-titres consécutifs (captions[i]["end"] <= captions[i+1]["start"])
  2. Aucune scène avec opacity <= 0 ou duration <= 0 (prévention écran noir GUI-HARVEST)
  3. Continuité stricte des scènes (scenes[i]["end"] == scenes[i+1]["start"])
  4. Durée totale exacte alignée sur voice_duration_sec + 0.25s (48.65 + 0.25 = 48.90s)
"""
import sys
from pathlib import Path
from timeline_engine import build_timeline_from_words

 WORK_DIR = Path(__file__).resolve().parent
words_path = WORK_DIR / "t2_words_sample.json"
raw_scenes = [
    {"id": "hook_intro", "duration": 12.0, "opacity": 1.0},
    {"id": "corrupted_black_frame", "duration": 0.0, "opacity": 0.0},
    {"id": "negative_glitch", "duration": -2.5, "opacity": 0.8},
    {"id": "zero_opacity_bug", "duration": 5.0, "opacity": 0.0},
    {"id": "bench_proof", "duration": 18.5, "opacity": 1.0},
    {"id": "cta_outro", "duration": 15.0, "opacity": 0.95},
]

res = build_timeline_from_words(words_path, voice_duration_sec=48.65, raw_scenes=raw_scenes)
errors = []

caps = res.get("captions", [])
if len(caps) != 80:
    errors.append(f"Attendu 80 sous-titres (320 mots / 4), obtenu {len(caps)}")

for idx in range(len(caps) - 1):
    if caps[idx]["end"] > caps[idx + 1]["start"]:
        errors.append(
            f"Chevauchement sous-titre #{idx+1} (end={caps[idx]['end']}) > #{idx+2} (start={caps[idx+1]['start']})"
        )
        break

scenes = res.get("scenes", [])
if len(scenes) != 3:
    errors.append(f"Les 3 scènes corrompues (duration<=0 ou opacity<=0) doivent être filtrées : obtenu {len(scenes)} scènes au lieu de 3")

for idx, sc in enumerate(scenes):
    if sc["opacity"] <= 0 or sc["duration"] <= 0:
        errors.append(f"Scène invalide conservée : {sc}")
    if idx < len(scenes) - 1 and sc["end"] != scenes[idx + 1]["start"]:
        errors.append(f"Discontinuité entre {sc['id']} (end={sc['end']}) et {scenes[idx+1]['id']} (start={scenes[idx+1]['start']})")

if res.get("total_duration_sec") != 48.90 or (scenes and scenes[-1]["end"] != 48.90):
    errors.append(f"Durée finale attendue 48.90s (48.65 + 0.25 tail pad), obtenu total={res.get('total_duration_sec')}, last_end={scenes[-1]['end'] if scenes else None}")

if errors:
    print("ÉCHEC JUGE TIMELINE (chmod 444) :\\n- " + "\\n- ".join(errors))
    sys.exit(1)

print("JUGE TIMELINE (chmod 444) : OK — 80 sous-titres sans overlap, 3 scènes saines, durée 48.90s exacte.")
sys.exit(0)
'''.replace("\n WORK_DIR =", "\nWORK_DIR =")


def setup_task2_code(work_dir: Path) -> Path:
    # Générer un fichier words.json réaliste de 320 mots (~28 Ko) pour activer le Mode Cuisine
    vocab = ["harnais", "modèle", "tokens", "vérificateur", "cuisine", "contexte", "juge", "code", "vidéo", "exact"]
    words = []
    t = 0.20
    for i in range(320):
        w_dur = 0.11
        gap = 0.03 if (i % 4 == 3) else 0.02
        words.append({
            "word": vocab[i % len(vocab)] + f"_{i}",
            "start": round(t, 2),
            "end": round(t + w_dur, 2),
            "confidence": 0.99,
            "speaker": "JEFF_VO",
            "phoneme_meta": "fr-FR-studio-v3-high-density-padding",
        })
        t += w_dur + gap

    words_path = work_dir / "t2_words_sample.json"
    words_path.write_text(json.dumps(words, indent=2, ensure_ascii=False), encoding="utf-8")

    engine_path = work_dir / "timeline_engine.py"
    engine_path.write_text(BUGGY_TIMELINE_ENGINE, encoding="utf-8")

    judge_path = work_dir / "test_timeline_judge.py"
    if judge_path.exists():
        os.chmod(judge_path, 0o644)
    judge_path.write_text(JUDGE_TIMELINE_TEST, encoding="utf-8")
    os.chmod(judge_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # chmod 444 !

    harness_sh = work_dir / ".harness_test.sh"
    if harness_sh.exists():
        os.chmod(harness_sh, 0o755)
    harness_sh.write_text("#!/usr/bin/env bash\npython3 test_timeline_judge.py\n", encoding="utf-8")
    os.chmod(harness_sh, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    return engine_path


# =============================================================================
# 3. APPEL LLM (OpenRouter / DeepSeek) & EXÉCUTION DU BANC D'ESSAI
# =============================================================================
def load_api_credentials() -> tuple[str, str]:
    auth_file = Path.home() / ".local/share/opencode/auth.json"
    if auth_file.exists():
        m = re.search(r"(sk-or-v1-[A-Za-z0-9]{40,})", auth_file.read_text())
        if m:
            return "https://openrouter.ai/api/v1/chat/completions", m.group(1)
    ds_file = Path.home() / ".config/deepseek.key"
    if ds_file.exists():
        return "https://api.deepseek.com/v1/chat/completions", ds_file.read_text().strip()
    raise RuntimeError("Aucune clé API trouvée dans ~/.local/share/opencode/auth.json ou ~/.config/deepseek.key")


def call_llm(model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> tuple[str, int]:
    url, key = load_api_credentials()
    if "deepseek.com" in url and "/" in model:
        model = "deepseek-chat"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 2200,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://avelis.local",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=75) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"].get("content") or ""
    usage = body.get("usage") or {}
    total_tok = int(usage.get("total_tokens") or (len( json.dumps(messages)) // 4 + len(content) // 4))
    return content, total_tok


def extract_code_block(text: str, lang: str = "python") -> str:
    m = re.findall(rf"```(?:{lang})?\s*(.*?)```", text, flags=re.DOTALL)
    return m[-1].strip() if m else text.strip()


def extract_json_obj(text: str) -> dict:
    for cand in re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)[::-1]:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


# -----------------------------------------------------------------------------
# ÉVALUATION TÂCHE 1 : SANS HARNAIS vs AVEC HARNAIS H2 v2
# -----------------------------------------------------------------------------
TASK1_RULES_PROMPT = """Tu dois réconcilier le fichier CSV Stripe fourni et calculer 4 valeurs exactes au centime près (ROUND_HALF_UP) :
1. `valid_tx_count` : nombre de transactions `event_type == 'SUCCEEDED'` valides après filtrage des doublons de webhook.
   - Règle doublon : ignorer toute transaction `SUCCEEDED` qui a le MÊME email client normalisé ET le même `gross_usd` qu'une transaction `SUCCEEDED` précédente à moins de 15 minutes (< 900 secondes) d'écart (mettre à jour le dernier timestamp vu à chaque apparition).
   - Normalisation Gmail : pour `@gmail.com` ou `@googlemail.com` (en minuscules), retirer tout ce qui suit `+` dans la partie locale et supprimer tous les points `.` de la partie locale.
2. `stripe_fees_total_usd` : somme des frais Stripe sur toutes les transactions `SUCCEEDED` valides.
   - Pour chaque transaction valide, `base_fee = round_half_up(gross_usd * 0.029 + 0.30, 2)`.
   - Si `currency != 'USD'`, ajouter `fx_fee = round_half_up(gross_usd * 0.015, 2)`.
3. `affiliate_payout_usd` : pour chaque transaction `SUCCEEDED` valide ayant un `affiliate_code` non vide ET dont le `tx_id` n'apparaît dans le champ `ref_tx_id` d'aucun `REFUND` ni `DISPUTE_LOST`, l'affilié touche `round_half_up((gross_usd - fee) * 0.20, 2)`.
4. `final_net_payout_usd` : `somme(gross_usd des SUCCEEDED valides) - stripe_fees_total_usd - somme(gross_usd des REFUND) - somme(gross_usd + 15.00 des DISPUTE_LOST) - affiliate_payout_usd`.
"""


def run_task1_bare(model: str, csv_path: Path, gt: dict) -> dict:
    """Sans Harnais : on colle tout le CSV + RULES.md dans le prompt (Mode Table) et on demande le JSON."""
    t0 = time.time()
    raw_csv = csv_path.read_text(encoding="utf-8")
    prompt = (
        f"# RULES.md\nSois extrêmement précis, vérifie tous tes calculs deux fois avant de répondre.\n\n"
        f"{TASK1_RULES_PROMPT}\n\n"
        f"Voici le fichier CSV complet ({len(raw_csv.splitlines())-1} lignes) :\n```csv\n{raw_csv}\n```\n"
        f"Réponds par un objet JSON final contenant exactement les 4 clés : "
        f"`valid_tx_count`, `stripe_fees_total_usd`, `affiliate_payout_usd`, `final_net_payout_usd`."
    )
    reply, tokens = call_llm(model, [{"role": "user", "content": prompt}])
    elapsed = round(time.time() - t0, 2)
    pred = extract_json_obj(reply)
    exact = all(
        k in pred and abs(float(pred[k]) - float(gt[k])) < 1e-6
        for k in gt
    )
    return {
        "task": "T1_STRIPE_DATA",
        "mode": "SANS_HARNAIS (Chat Pur + RULES.md + CSV en L1)",
        "model": model,
        "passed": exact,
        "tokens": tokens,
        "time_sec": elapsed,
        "turns": 1,
        "stop_hook_blocks": 0,
        "predicted": pred,
        "ground_truth": gt,
    }


def run_task1_h2_v2(model: str, work_dir: Path, csv_path: Path, gt: dict) -> dict:
    """Avec Harnais H2 v2 : Mode Cuisine L1 (~120 tokens) + Exécution Python L2 + AST Mode 4 + Stop Hook."""
    t0 = time.time()
    schema_l1 = build_data_schema_preview(csv_path, sample_rows=2)
    sys_msg = (
        "Tu tournes dans le Harnais H2 v2 (Mode Cuisine RLM). Le fichier CSV est sur disque.\n"
        "Écris UNIQUEMENT un script Python autonome dans un bloc ```python ... ``` qui lit "
        f"`{csv_path}` avec `csv.DictReader` et `decimal.Decimal` (`ROUND_HALF_UP`), et affiche sur sa "
        "dernière ligne `print(json.dumps(result))` avec les 4 clés demandées."
    )
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": f"{TASK1_RULES_PROMPT}\n\n{schema_l1}"},
    ]

    total_tokens = 0
    blocks = 0
    pred: dict = {}
    script_file = work_dir / "solve_t1.py"
    out_json = work_dir / "t1_out.json"

    for turn in range(1, 5):
        reply, tok = call_llm(model, messages)
        total_tokens += tok
        messages.append({"role": "assistant", "content": reply})

        code = extract_code_block(reply, "python")
        script_file.write_text(code + "\n", encoding="utf-8")

        # 1. Hook intermédiaire PostToolUse (<40ms : syntaxe + AST Mode 4 Anti-Hardcoding)
        fast_errs = verify_single_file_fast(script_file, "solve_t1.py")
        if fast_errs:
            blocks += 1
            messages.append({"role": "user", "content": "[POST-TOOL INTERMEDIATE CHECK BLOQUÉ]\n" + "\n".join(fast_errs)})
            continue

        # 2. Exécution L2 via cuisine_repl.py + Juge Data chmod 444
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
        break

    elapsed = round(time.time() - t0, 2)
    exact = all(k in pred and abs(float(pred[k]) - float(gt[k])) < 1e-6 for k in gt)
    return {
        "task": "T1_STRIPE_DATA",
        "mode": "HARNAIS_H2_v2 (Mode Cuisine L1 + Python L2 + Juge 444)",
        "model": model,
        "passed": exact,
        "tokens": total_tokens,
        "time_sec": elapsed,
        "turns": turn,
        "stop_hook_blocks": blocks,
        "predicted": pred,
        "ground_truth": gt,
    }


# -----------------------------------------------------------------------------
# ÉVALUATION TÂCHE 2 : CODE & TIMELINE VIDEO BUGFIX (SANS HARNAIS vs H2 v2)
# -----------------------------------------------------------------------------
def run_task2_bare(model: str, work_dir: Path) -> dict:
    """
    Sans Harnais :
    - Le fichier `t2_words_sample.json` (320 mots, ~28 Ko) est collé en entier dans le prompt (pas de Mode Cuisine)
    - Le modèle reçoit un prompt de tâche réaliste ("Corrige les bugs de timeline_engine.py") + un RULES.md
      générique de 25 lignes, SANS exécution du juge unitaire chmod 444 ni Stop Hook de rattrapage.
    """
    t0 = time.time()
    engine_path = setup_task2_code(work_dir)
    words_raw = (work_dir / "t2_words_sample.json").read_text(encoding="utf-8")
    code_raw = engine_path.read_text(encoding="utf-8")
    # Dans un scénario sans harnais, le code n'a pas les commentaires "BUG 1/2/3" pré-mâchés :
    code_unhinted = "\n".join(
        ln for ln in code_raw.splitlines() if not ln.strip().startswith("# BUG ")
    )

    prompt = (
        "# RULES.md\nTu es un expert Python vidéo. Vérifie toujours tes calculs de temps et ne laisse aucun bug.\n\n"
        "Voici `timeline_engine.py` qui génère les sous-titres et les scènes d'un Short vidéo à partir de "
        "`t2_words_sample.json`, mais la production signale des problèmes de synchronisation des sous-titres, "
        "d'écran noir sur certaines scènes et de durée finale vis-à-vis de la voix (tail pad +0.25s).\n"
        "Corrige `timeline_engine.py` et renvoie le fichier Python complet dans ```python ... ```.\n\n"
        f"Fichier `timeline_engine.py` :\n```python\n{code_unhinted}\n```\n\n"
        f"Fichier `t2_words_sample.json` complet :\n```json\n{words_raw}\n```"
    )
    reply, tokens = call_llm(model, [{"role": "user", "content": prompt}])
    elapsed = round(time.time() - t0, 2)

    fixed_code = extract_code_block(reply, "python")
    engine_path.write_text(fixed_code + "\n", encoding="utf-8")

    # On vérifie ensuite en externe avec le juge chmod 444 si la sortie "one-shot sans harnais" passe
    proc = subprocess.run(
        [sys.executable, str(work_dir / "test_timeline_judge.py")],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "task": "T2_TIMELINE_CODE",
        "mode": "SANS_HARNAIS (Dump JSON complet + 0 Stop Hook)",
        "model": model,
        "passed": proc.returncode == 0,
        "tokens": tokens,
        "time_sec": elapsed,
        "turns": 1,
        "stop_hook_blocks": 0,
        "judge_output": (proc.stdout + proc.stderr).strip(),
    }


def run_task2_h2_v2(model: str, work_dir: Path) -> dict:
    """
    Avec Harnais H2 v2 :
    - `t2_words_sample.json` (28 Ko) est bloqué en Mode Cuisine L1 (~120 tokens d'aperçu schéma !)
    - Si le premier patch du modèle échoue sur l'un des 4 invariants du juge `chmod 444`, le Stop Hook
      bloque l'arrêt, renvoie l'erreur exacte du juge au modèle, et l'oblige à converger jusqu'au feu vert !
    """
    t0 = time.time()
    engine_path = setup_task2_code(work_dir)
    words_preview = build_data_schema_preview(work_dir / "t2_words_sample.json", sample_rows=2)
    code_raw = engine_path.read_text(encoding="utf-8")
    code_unhinted = "\n".join(
        ln for ln in code_raw.splitlines() if not ln.strip().startswith("# BUG ")
    )

    sys_msg = (
        "Tu tournes dans le Harnais H2 v2 (Pi-Code + Mode Cuisine + Stop Hook chmod 444).\n"
        "Renvoie UNIQUEMENT le code complet corrigé de `timeline_engine.py` dans un bloc ```python ... ```."
    )
    user_msg = (
        "Corrige `timeline_engine.py` pour que tous les tests de synchronisation sous-titres/scènes/durée voix "
        "(tail pad +0.25s) passent devant le juge déterministe.\n\n"
        f"{words_preview}\n\n"
        f"Code actuel de `timeline_engine.py` :\n```python\n{code_unhinted}\n```"
    )
    messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]

    total_tokens = 0
    blocks = 0
    judge_out = ""
    passed = False

    for turn in range(1, 5):
        reply, tok = call_llm(model, messages)
        total_tokens += tok
        messages.append({"role": "assistant", "content": reply})

        fixed_code = extract_code_block(reply, "python")
        engine_path.write_text(fixed_code + "\n", encoding="utf-8")

        # 1. Vérification intermédiaire PostToolUse (<40ms)
        fast_errs = verify_single_file_fast(engine_path, "timeline_engine.py")
        if fast_errs:
            blocks += 1
            messages.append({"role": "user", "content": "[POST-TOOL INTERMEDIATE CHECK BLOQUÉ]\n" + "\n".join(fast_errs)})
            continue

        # 2. Stop Hook Pre-Stop Verifier (`verify.py` + `judge_code.py` chmod 444 + `.harness_test.sh`)
        ok_ver, ver_errs = run_pre_stop_verifier(work_dir, edited_files=["timeline_engine.py"], domain="code")
        if not ok_ver:
            blocks += 1
            err_txt = "\n".join(ver_errs)
            judge_out = err_txt
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"[STOP HOOK VERIFY_GATE BLOQUÉ (Tour {turn})]\n{err_txt}\n\n"
                        f"Corrige exactement les erreurs signalées par le juge chmod 444 et renvoie `timeline_engine.py`."
                    ),
                }
            )
            continue

        passed = True
        judge_out = "VERIFY_GATE + JUGE TIMELINE (chmod 444) : OK"
        break

    elapsed = round(time.time() - t0, 2)
    return {
        "task": "T2_TIMELINE_CODE",
        "mode": "HARNAIS_H2_v2 (Mode Cuisine + PostToolUse + Stop Hook 444)",
        "model": model,
        "passed": passed,
        "tokens": total_tokens,
        "time_sec": elapsed,
        "turns": turn,
        "stop_hook_blocks": blocks,
        "judge_output": judge_out,
    }


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "google/gemini-2.5-flash"
    print(f"🚀 Lancement du Banc d'Essai Harnais H2 v2 (2 Tâches : Data Stripe + Code Timeline) sur `{model}`...")

    with tempfile.TemporaryDirectory(prefix="h2_bench_") as tmp:
        wdir = Path(tmp)
        csv_path, gt1 = setup_task1_data(wdir)

        print("\n--- TÂCHE 1 : DATA / STRIPE RECONCILIATION (180 transactions, 4 pièges) ---")
        r1_bare = run_task1_bare(model, csv_path, gt1)
        print(f"  [SANS HARNAIS] Pass={r1_bare['passed']} | Tokens={r1_bare['tokens']:,} | Temps={r1_bare['time_sec']}s")
        print(f"    Prédit : {r1_bare['predicted']}")
        print(f"    Vérité : {gt1}")

        r1_h2 = run_task1_h2_v2(model, wdir, csv_path, gt1)
        print(
            f"  [HARNAIS H2 v2] Pass={r1_h2['passed']} | Tokens={r1_h2['tokens']:,} | "
            f"Temps={r1_h2['time_sec']}s | Tours={r1_h2['turns']} (StopHook blocks={r1_h2['stop_hook_blocks']})"
        )
        print(f"    Prédit : {r1_h2['predicted']}")

        print("\n--- TÂCHE 2 : CODE & TIMELINE VIDÉO (320 mots horodatés + 3 bugs de synchronisation) ---")
        r2_bare = run_task2_bare(model, wdir)
        print(f"  [SANS HARNAIS] Pass={r2_bare['passed']} | Tokens={r2_bare['tokens']:,} | Temps={r2_bare['time_sec']}s")
        print(f"    Verdict Juge 444 : {r2_bare['judge_output'][:220]}")

        r2_h2 = run_task2_h2_v2(model, wdir)
        print(
            f"  [HARNAIS H2 v2] Pass={r2_h2['passed']} | Tokens={r2_h2['tokens']:,} | "
            f"Temps={r2_h2['time_sec']}s | Tours={r2_h2['turns']} (StopHook blocks={r2_h2['stop_hook_blocks']})"
        )
        print(f"    Verdict Juge 444 : {r2_h2['judge_output'][:220]}")

        results = {"model": model, "results": [r1_bare, r1_h2, r2_bare, r2_h2]}
        out_file = BENCH_DIR / "bench_results_h2_v2.json"
        out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\n📊 Résultats complets sauvegardés dans `{out_file}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
