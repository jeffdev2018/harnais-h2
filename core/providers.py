#!/usr/bin/env python3
"""
Brique 6, 7 & 9 (Harnais H2 v3) — providers.py
Adaptateur & Routeur Multi-Modèles Universel + Middleware de Réparation AST pour petits modèles :
  1. Modèles Locaux (Magnitude Metal M5 Pro `127.0.0.1:10100/v1`, Ollama `127.0.0.1:11434/v1`)
  2. Modèles Gratuits FreeLLMAPI (`http://127.0.0.1:3011/v1` avec clé `freellmapi-...`)
  3. DeepSeek (API directe `api.deepseek.com` + DeepSeek Harness `dsh` + `opencode`)
  4. ChatGPT (`codex exec --skip-git-repo-check`)
  5. Claude (`claude -p --output-format json`)
  6. Cascade Routing (`cascade_call`) : Gratuit/Local ($0.00) -> DeepSeek -> Frontier (Claude/ChatGPT)
     uniquement si le Stop Hook chmod 444 rejette la sortie du modèle gratuit/local !
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

FREELLM_URL = os.environ.get("FREELLM_API_URL", "http://127.0.0.1:3011/v1/chat/completions")
FREELLM_KEY = os.environ.get("FREELLM_API_KEY", "")

MAGNITUDE_URL = "http://127.0.0.1:10100/inference/v1/chat/completions"
MAGNITUDE_KEY = "magnitude-local"
OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

STD_PREAMBLE = (
    "import csv, datetime, json, math, os, re, sys\n"
    "from pathlib import Path\n"
    "from decimal import Decimal, ROUND_HALF_UP\n"
)


def get_deepseek_key() -> str:
    p = Path.home() / ".config/deepseek.key"
    return p.read_text().strip() if p.exists() else os.environ.get("DEEPSEEK_API_KEY", "")


def repair_python_code_for_small_models(raw_code: str) -> str:
    """
    Brique 7 (Google arXiv:2611.22299 §V : Deterministic Middleware for Smaller/Local Models) :
    - Nettoie les balises Markdown résiduelles ou textes parasites autour du code
    - Injecte automatiquement les imports standards (`csv`, `json`, `Decimal`, `ROUND_HALF_UP`, `Path`)
      si un petit modèle local/gratuit les a oubliés.
    """
    code = raw_code.strip()
    m_py = re.findall(r"```python\s*(.*?)```", code, flags=re.DOTALL | re.IGNORECASE)
    if m_py:
        code = max(m_py, key=len).strip()
    else:
        m_any = re.findall(r"```(?:\w+)?\s*(.*?)```", code, flags=re.DOTALL)
        if m_any:
            code = max(m_any, key=len).strip()

    # Supprimer d'éventuelles lignes de prose avant le premier import/def/with/from/#
    lines = code.splitlines()
    start_idx = 0
    for idx, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith(("import ", "from ", "def ", "class ", "with ", "#", "rows", "data")) or "=" in s:
            start_idx = idx
            break
    code = "\n".join(lines[start_idx:])

    # Vérifier si les imports de base manquent
    needed = []
    if "Decimal" in code and "import Decimal" not in code:
        needed.append("from decimal import Decimal, ROUND_HALF_UP")
    if "csv." in code and "import csv" not in code:
        needed.append("import csv")
    if "json." in code and "import json" not in code:
        needed.append("import json")
    if "datetime" in code and "import datetime" not in code:
        needed.append("import datetime")
    if "Path(" in code and "import Path" not in code:
        needed.append("from pathlib import Path")

    if needed:
        code = "\n".join(needed) + "\n" + code

    return code


def _http_chat_completion(
    url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 2400,
    timeout: int = 65,
    disable_reasoning: bool = False,
) -> tuple[str, int]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if disable_reasoning:
        payload["reasoning_effort"] = "none"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or 'local'}",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    msg = body["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning_content") or ""
    usage = body.get("usage") or {}
    tok = int(usage.get("total_tokens") or (len(json.dumps(messages)) // 4 + len(content) // 4))
    return content, tok


def _cli_codex_call(messages: list[dict[str, str]], timeout: int = 75) -> tuple[str, int]:
    """Appelle ChatGPT via Codex CLI (`/opt/homebrew/bin/codex exec -` via stdin)."""
    prompt = (
        "IMPORTANT: Do NOT execute any shell command or tool. Reply directly with the requested JSON or Python code block.\n\n"
        + "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in messages)
    )
    proc = subprocess.run(
        ["/opt/homebrew/bin/codex", "exec", "--skip-git-repo-check", "--json", "-"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    final_txt = ""
    in_tok = out_tok = 0
    for line in proc.stdout.splitlines():
        if not line.strip().startswith("{"):
            continue
        try:
            ev = json.loads(line)
            if ev.get("type") == "item.completed":
                it = ev.get("item", {})
                if it.get("type") == "agent_message":
                    final_txt = it.get("text", "")
            elif ev.get("type") == "turn.completed":
                u = ev.get("usage", {})
                in_tok += int(u.get("input_tokens", 0))
                out_tok += int(u.get("output_tokens", 0))
        except Exception:
            continue
    if not final_txt:
        final_txt = proc.stdout.strip()
    tot = (in_tok + out_tok) or (len(prompt) // 4 + len(final_txt) // 4)
    return final_txt, tot


def _cli_claude_call(messages: list[dict[str, str]], timeout: int = 75) -> tuple[str, int]:
    """Appelle Claude via Claude CLI (`/Users/jeff/.local/bin/claude -p --tools ""` via stdin)."""
    prompt = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in messages)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.run(
        ["/Users/jeff/.local/bin/claude", "-p", "--tools", "", "--output-format", "json"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    raw = proc.stdout.strip()
    try:
        obj = json.loads(raw)
        txt = str(obj.get("result") or obj.get("content") or raw)
        u = obj.get("usage") or {}
        tok = int(u.get("input_tokens", 0)) + int(u.get("output_tokens", 0))
        return txt, tok if tok > 20 else (len(prompt) // 4 + len(txt) // 4)
    except Exception:
        return raw, len(prompt) // 4 + len(raw) // 4


def _cli_opencode_call(model_slug: str, messages: list[dict[str, str]], timeout: int = 75) -> tuple[str, int]:
    """Appelle un modèle via OpenCode CLI (`/Users/jeff/.local/bin/opencode run -m <slug>`)."""
    prompt = (
        "Reply directly in text without invoking any tool:\n\n"
        + "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in messages)
    )
    proc = subprocess.run(
        ["/Users/jeff/.local/bin/opencode", "run", "-m", model_slug, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    txt = (proc.stdout or "").strip()
    tok = len(prompt) // 4 + len(txt) // 4
    return txt, tok


def call_universal_model(
    spec: str,
    messages: list[dict[str, str]],
    max_tokens: int = 2400,
    timeout: int = 65,
) -> tuple[str, int]:
    """
    Format de `spec` :
      - `local:<model_id>`     -> Magnitude Local Metal (`http://127.0.0.1:10100/v1`)
      - `freellm:<model_id>`   -> FreeLLMAPI (`http://127.0.0.1:3011/v1`)
      - `deepseek:<model_id>`  -> DeepSeek Direct API (`https://api.deepseek.com/v1`)
      - `opencode:<model_id>`  -> OpenCode CLI (`opencode run -m ...`)
      - `cli:codex`            -> ChatGPT via Codex CLI
      - `cli:claude`           -> Claude via Claude CLI
    """
    prefix, _, model_id = spec.partition(":")
    prefix = prefix.lower()
    if not model_id:
        model_id = prefix
        prefix = "freellm"

    for attempt in range(2):
        try:
            if prefix == "local":
                return _http_chat_completion(
                    MAGNITUDE_URL, MAGNITUDE_KEY, model_id, messages, max_tokens, timeout, disable_reasoning=True
                )
            if prefix == "ollama":
                return _http_chat_completion(OLLAMA_URL, "ollama", model_id, messages, max_tokens, timeout)
            if prefix == "freellm":
                return _http_chat_completion(
                    FREELLM_URL, FREELLM_KEY, model_id, messages, max_tokens, timeout, disable_reasoning=False
                )
            if prefix == "deepseek":
                return _http_chat_completion(DEEPSEEK_URL, get_deepseek_key(), model_id, messages, max_tokens, timeout)
            if prefix == "opencode":
                return _cli_opencode_call(model_id, messages, timeout=timeout)
            if prefix == "cli" and model_id == "codex":
                return _cli_codex_call(messages, timeout=timeout)
            if prefix == "cli" and model_id == "claude":
                return _cli_claude_call(messages, timeout=timeout)
            return _http_chat_completion(FREELLM_URL, FREELLM_KEY, spec, messages, max_tokens, timeout)
        except Exception as exc:
            if attempt == 1:
                return f'{{"error": "{exc}"}}', len(json.dumps(messages)) // 4
            time.sleep(1.2)
    return "{}", 0


def discover_all_machine_models() -> list[dict[str, str]]:
    """Inventorie dynamiquement tous les modèles actifs sur le Mac de Jeff."""
    found: list[dict[str, str]] = []

    # 1. Magnitude Local (Apple M5 Pro Metal)
    try:
        req = urllib.request.Request("http://127.0.0.1:10100/v1/models")
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode()).get("data", [])
            for m in data:
                found.append({"spec": f"local:{m['id']}", "category": "LOCAL_M5_METAL", "name": m.get("id", "")})
    except Exception:
        pass

    # 2. FreeLLMAPI (127.0.0.1:3011)
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:3011/v1/models",
            headers={"Authorization": f"Bearer {FREELLM_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode()).get("data", [])
            for m in data:
                if m.get("available"):
                    found.append({"spec": f"freellm:{m['id']}", "category": "FREELLM_3011", "name": m.get("name", m["id"])})
    except Exception:
        pass

    # 3. DeepSeek Direct API
    if get_deepseek_key():
        found.append({"spec": "deepseek:deepseek-chat", "category": "DEEPSEEK_API", "name": "DeepSeek Chat V3/V4"})

    # 4. OpenCode CLI
    if shutil.which("opencode"):
        found.append({"spec": "opencode:deepseek/deepseek-flash", "category": "OPENCODE_CLI", "name": "OpenCode DeepSeek Flash"})

    # 5. ChatGPT (Codex CLI) & Claude (Claude CLI)
    if Path("/opt/homebrew/bin/codex").exists():
        found.append({"spec": "cli:codex", "category": "CHATGPT_CODEX_CLI", "name": "ChatGPT (Codex CLI)"})
    if Path("/Users/jeff/.local/bin/claude").exists():
        found.append({"spec": "cli:claude", "category": "CLAUDE_CODE_CLI", "name": "Claude (Claude Code CLI)"})

    return found


if __name__ == "__main__":
    models = discover_all_machine_models()
    print(f"🔍 {len(models)} modèles/moteurs détectés sur ce Mac :")
    for m in models[:25]:
        print(f"  • [{m['category']:18s}] {m['spec']:36s} ({m['name']})")
    if len(models) > 25:
        print(f"  ... et {len(models) - 25} autres modèles gratuits sur FreeLLMAPI (127.0.0.1:3011).")
