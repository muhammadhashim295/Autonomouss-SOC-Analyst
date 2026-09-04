#!/usr/bin/env python3
"""End-to-end agent test — run the 6 GUIDE demo alerts through the real
three-provider client pipeline and print each agent's verdict.

Primary Agent  -> GroqClient      (live if the Groq key/org allows the model)
Secondary Agent-> CerebrasClient  (live if Cerebras quota allows; else fallback)

This exercises the SAME code paths the SSE pipeline uses: real investigation
skills (OTX / ATT&CK / correlation / deviation), the shared prompt builders,
token streaming, ``parse_agent_response``, and the deterministic fallback.
It does NOT require the FastAPI server or Supabase (similar-case retrieval is
stubbed to []), so it isolates agent/provider behaviour.

Run from backend/:
    .venv\\Scripts\\python.exe scripts\\test_live_agents.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Live model output can contain unicode (em-dashes, curly quotes) that the
# Windows cp1252 console cannot encode — force UTF-8 and replace anything odd.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.services.agent_prompts import build_investigation_prompt, build_reinvestigation_prompt
from app.services.cerebras_client import get_cerebras_client
from app.services.groq_client import get_groq_client
from app.services.investigation import classify_impact, parse_agent_response
from app.services.skills import (
    correlate_logs,
    detect_deviation,
    enrich_iocs,
    map_attack_techniques,
)

SAMPLES = Path(__file__).resolve().parent.parent / "app" / "data" / "sample_alerts.json"

# Capture client warnings so we can label each result LIVE vs FALLBACK.
_FALLBACK_MARKERS = ("fallback engaged", "using deterministic fallback", "empty stream")
_fallback_flags: list[bool] = [False]


class _FallbackWatcher(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage().lower()
        if any(m in msg for m in _FALLBACK_MARKERS):
            _fallback_flags[0] = True


logging.basicConfig(level=logging.WARNING, format="    log: %(message)s")
for name in ("app.services.groq_client", "app.services.cerebras_client"):
    logging.getLogger(name).addHandler(_FallbackWatcher())


def _run_skills(alert_type: str, payload: dict) -> dict:
    return {
        "otx_enrichment": enrich_iocs(payload),
        "attack_mapping": map_attack_techniques(alert_type, payload),
        "log_correlation": correlate_logs(alert_type, payload),
        "behavioral_deviation": detect_deviation(alert_type, payload),
    }


def _snip(text: str, n: int = 220) -> str:
    text = " ".join(str(text).split())
    return text[:n] + ("..." if len(text) > n else "")


def main() -> None:
    alerts = json.loads(SAMPLES.read_text(encoding="utf-8"))
    groq = get_groq_client()
    cerebras = get_cerebras_client()

    print("=" * 72)
    print("  GUIDE DEMO ALERTS -> LIVE THREE-PROVIDER PIPELINE")
    print(f"  Primary={groq.provider_name} (model auto)   Secondary={cerebras.provider_name}")
    print("=" * 72)

    summary = []
    for alert in alerts:
        sid = alert["source_alert_id"]
        atype = alert["alert_type"]
        payload = alert["raw_payload"]
        print(f"\n{'-' * 72}\n  {sid}  [{atype}]\n{'-' * 72}")

        enrichment = _run_skills(atype, payload)
        impact = classify_impact(atype, payload)
        print(f"  impact classification (enforced): {impact}")

        # ── Primary Agent (Groq) ──
        _fallback_flags[0] = False
        p_session = groq.create_session(agent_id="primary")
        p_prompt = build_investigation_prompt(alert, atype, payload, enrichment, [])
        groq.send_message(p_session["id"], p_prompt)
        p_text = groq.stream_response(p_session["id"])
        p_live = not _fallback_flags[0]
        p_parsed = parse_agent_response(p_text)
        print(f"  PRIMARY  (groq)     : {'LIVE' if p_live else 'FALLBACK'}")
        print(f"     verdict={p_parsed.get('verdict')}  confidence={p_parsed.get('confidence')}  "
              f"attack={p_parsed.get('attack_technique')}")
        print(f"     reasoning: {_snip(p_parsed.get('reasoning', ''))}")
        print(f"     self_audit: {_snip(p_parsed.get('self_audit', ''), 160)}")

        # ── Secondary Agent (Cerebras) ──
        primary_result = {"agent_response": p_text, "parsed": p_parsed,
                          "enrichment": enrichment, "impact_level": impact,
                          "similar_cases": [], "session_id": p_session["id"]}
        _fallback_flags[0] = False
        s_session = cerebras.create_session(agent_id="secondary")
        s_prompt = build_reinvestigation_prompt(alert, atype, payload, enrichment, primary_result, [])
        cerebras.send_message(s_session["id"], s_prompt)
        s_text = cerebras.stream_response(s_session["id"])
        s_live = not _fallback_flags[0]
        s_parsed = parse_agent_response(s_text)
        print(f"  SECONDARY(cerebras) : {'LIVE' if s_live else 'FALLBACK'}")
        print(f"     secondary_verdict={s_parsed.get('secondary_verdict')}  "
              f"confidence={s_parsed.get('confidence')}  impact={s_parsed.get('impact_level')}")
        print(f"     reasoning: {_snip(s_parsed.get('reasoning', ''))}")

        summary.append({
            "id": sid, "type": atype, "impact": impact,
            "primary_mode": "LIVE" if p_live else "FALLBACK",
            "primary_verdict": p_parsed.get("verdict"),
            "primary_conf": p_parsed.get("confidence"),
            "secondary_mode": "LIVE" if s_live else "FALLBACK",
            "secondary_verdict": s_parsed.get("secondary_verdict"),
        })

    print(f"\n{'=' * 72}\n  SUMMARY\n{'=' * 72}")
    hdr = f"  {'ALERT':18s} {'IMPACT':12s} {'PRIMARY':16s} {'SECONDARY':16s}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in summary:
        p = f"{r['primary_verdict']}({r['primary_mode'][0]})"
        s = f"{r['secondary_verdict']}({r['secondary_mode'][0]})"
        print(f"  {r['id']:18s} {r['impact']:12s} {p:16s} {s:16s}")
    print("\n  (L)=LIVE model output, (F)=deterministic fallback (provider blocked)")
    print("=" * 72)


if __name__ == "__main__":
    main()
