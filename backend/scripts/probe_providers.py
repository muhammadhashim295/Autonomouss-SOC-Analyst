#!/usr/bin/env python3
"""Three-provider health probe + retry-with-backoff demonstration.

Final architecture (one provider per role):
  - Groq                  -> Primary Alert Triage Agent
  - Cerebras              -> Secondary Deep Investigation Agent
  - Cloudflare Workers AI -> live alert generator

This script makes real (tiny) API calls to each provider so you can confirm
credential/account status before a demo, and it exercises the shared
``post_with_backoff`` helper against a simulated rate-limit to prove the
retry-with-exponential-backoff requirement actually triggers and recovers.

Run from the backend/ directory:
    .venv\\Scripts\\python.exe scripts\\probe_providers.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from app.core.config import settings
from app.services.provider_common import post_with_backoff

logging.basicConfig(level=logging.INFO, format="    %(levelname)s %(message)s")

PASS, WARN, FAIL = "[PASS]", "[WARN]", "[FAIL]"


def section(title: str) -> None:
    print(f"\n{'=' * 66}\n  {title}\n{'=' * 66}")


# ── Groq — Primary Agent ──────────────────────────────────────────────────────


def probe_groq() -> None:
    section("GROQ — Primary Alert Triage Agent")
    key = settings.groq_api_key
    if not key:
        print(f"  {FAIL} GROQ_API_KEY not set")
        return
    print(f"  model = {settings.groq_model}")
    h = {"Authorization": f"Bearer {key}"}
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers=h, timeout=30)
        print(f"  {PASS if r.status_code == 200 else FAIL} GET /models -> {r.status_code}")
    except requests.RequestException as exc:
        print(f"  {FAIL} GET /models connection error: {exc}")
        return
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=h,
            json={
                "model": settings.groq_model,
                "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
                "max_tokens": 5,
                "stream": False,
            },
            timeout=40,
        )
        ok = r.status_code == 200
        print(f"  {PASS if ok else FAIL} POST /chat/completions -> {r.status_code}")
        if not ok:
            print(f"        body: {r.text[:280]}")
            if r.status_code == 403:
                print("        -> 403 org-blocked: enable the model in Groq console org settings.")
        else:
            choice = r.json().get("choices", [{}])[0]
            print(f"        reply: {str(choice.get('message', {}).get('content'))[:80]!r}")
    except requests.RequestException as exc:
        print(f"  {FAIL} POST /chat/completions connection error: {exc}")


# ── Cerebras — Secondary Agent ────────────────────────────────────────────────


def probe_cerebras() -> None:
    section("CEREBRAS — Secondary Deep Investigation Agent")
    key = settings.cerebras_api_key
    if not key:
        print(f"  {FAIL} CEREBRAS_API_KEY not set")
        return
    print(f"  model = {settings.cerebras_model}")
    h = {"Authorization": f"Bearer {key}"}
    try:
        r = requests.get("https://api.cerebras.ai/v1/models", headers=h, timeout=30)
        print(f"  {PASS if r.status_code == 200 else FAIL} GET /models -> {r.status_code}")
    except requests.RequestException as exc:
        print(f"  {FAIL} GET /models connection error: {exc}")
        return
    try:
        r = requests.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers=h,
            json={
                "model": settings.cerebras_model,
                "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
                "max_tokens": 5,
                "stream": False,
            },
            timeout=40,
        )
        ok = r.status_code == 200
        print(f"  {PASS if ok else FAIL} POST /chat/completions -> {r.status_code}")
        if not ok:
            print(f"        body: {r.text[:280]}")
            if r.status_code == 402:
                print("        -> 402 quota: enable Cerebras inference quota/billing for this key.")
        else:
            choice = r.json().get("choices", [{}])[0]
            print(f"        reply: {str(choice.get('message', {}).get('content'))[:80]!r}")
    except requests.RequestException as exc:
        print(f"  {FAIL} POST /chat/completions connection error: {exc}")


# ── Cloudflare Workers AI — live alert generator ──────────────────────────────


def probe_cloudflare() -> None:
    section("CLOUDFLARE WORKERS AI — live alert generator")
    token = settings.cloudflare_api_token
    account_id = settings.cloudflare_account_id
    if not token:
        print(f"  {FAIL} CLOUDFLARE_API_TOKEN not set")
        return
    h = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get("https://api.cloudflare.com/client/v4/user/tokens/verify", headers=h, timeout=30)
        j = r.json() if r.status_code == 200 else {}
        status = j.get("result", {}).get("status")
        print(f"  {PASS if status == 'active' else WARN} token verify -> {r.status_code} (status={status})")
    except requests.RequestException as exc:
        print(f"  {FAIL} token verify connection error: {exc}")
        return

    if not account_id:
        print(f"  {WARN} CLOUDFLARE_ACCOUNT_ID not set — live feed cannot run.")
        try:
            r = requests.get("https://api.cloudflare.com/client/v4/accounts", headers=h, timeout=30)
            accts = r.json().get("result", []) if r.status_code == 200 else []
            total = r.json().get("result_info", {}).get("total_count") if r.status_code == 200 else None
            print(f"        GET /accounts -> {r.status_code} (total_count={total}, listed={len(accts)})")
            for a in accts[:5]:
                print(f"        account: {a.get('id')}  ({a.get('name')})")
            if not accts:
                print("        -> Token cannot list accounts. Copy the Account ID from the")
                print("           Cloudflare dashboard (right-hand panel) into .env.")
        except requests.RequestException as exc:
            print(f"        GET /accounts connection error: {exc}")
        return

    print(f"  account_id = {account_id}  model = {settings.cloudflare_model}")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{settings.cloudflare_model}"
    try:
        r = requests.post(url, headers=h, json={"prompt": "Say OK", "max_tokens": 5}, timeout=40)
        ok = r.status_code == 200
        print(f"  {PASS if ok else FAIL} POST /ai/run -> {r.status_code}")
        print(f"        body: {r.text[:280]}")
    except requests.RequestException as exc:
        print(f"  {FAIL} POST /ai/run connection error: {exc}")


# ── Retry-with-backoff demonstration (simulated rate limit) ───────────────────


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = f"simulated HTTP {status_code}"

    def json(self) -> dict[str, Any]:
        return {}

    def close(self) -> None:
        return None


class _FakeSession:
    """Returns a scripted sequence of status codes, then records call times."""

    def __init__(self, statuses: list[int]) -> None:
        self._statuses = list(statuses)
        self.call_times: list[float] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.call_times.append(time.monotonic())
        code = self._statuses.pop(0) if self._statuses else 200
        return _FakeResponse(code)


def probe_retry_backoff() -> None:
    section("RETRY-WITH-BACKOFF — simulated rate limit (429 -> 429 -> 200)")
    print("  Shared helper post_with_backoff() is used by ALL THREE providers.")
    print(f"  Config: max_retries={settings.provider_max_retries}, "
          f"base={settings.provider_backoff_base_seconds}s -> delays 1s, 2s, 4s")

    sess = _FakeSession([429, 429, 200])
    start = time.monotonic()
    resp = post_with_backoff(sess, "https://example.invalid/run", provider="probe",
                             json={"x": 1}, stream=False, timeout=5)
    elapsed = time.monotonic() - start

    recovered = resp.status_code == 200
    gaps = [round(sess.call_times[i + 1] - sess.call_times[i], 2) for i in range(len(sess.call_times) - 1)]
    print(f"  {PASS if recovered else FAIL} recovered with 200 after {len(sess.call_times) - 1} retries "
          f"(total {elapsed:.2f}s)")
    print(f"        observed backoff gaps between attempts: {gaps} (expected ~[1.0, 2.0])")
    print(f"        attempts made: {len(sess.call_times)} (initial + retries)")

    # Permanent errors must NOT be retried (backoff cannot fix 402/403/404).
    section("RETRY POLICY — permanent error (403) must NOT be retried")
    sess2 = _FakeSession([403])
    resp2 = post_with_backoff(sess2, "https://example.invalid/run", provider="probe",
                              json={"x": 1}, stream=False, timeout=5)
    no_retry = len(sess2.call_times) == 1
    print(f"  {PASS if no_retry else FAIL} 403 returned immediately after {len(sess2.call_times)} attempt(s) "
          f"(status={resp2.status_code}) — caller falls back deterministically")


def main() -> None:
    print("=" * 66)
    print("  THREE-PROVIDER HEALTH PROBE — Autonomous SOC Analyst Framework")
    print("=" * 66)
    probe_groq()
    probe_cerebras()
    probe_cloudflare()
    probe_retry_backoff()
    print(f"\n{'=' * 66}\n  Probe complete.\n{'=' * 66}\n")


if __name__ == "__main__":
    main()
