"""Phase 7 — Parser unit test + re-run triage."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.investigation import parse_agent_response, classify_impact

# ── Test 1: Parser with agent echoing prompt ──────────────────────────────
# Simulates agent echoing the prompt then giving actual answer
echoed_text = (
    "Investigate the following security alert. You MUST produce a "
    "structured investigation report...\n\n"
    "**Verdict:** false_positive OR true_positive\n\n"
    "**Confidence:** a number between 0.0 and 1.0\n\n"
    "--- Actual Response ---\n\n"
    "**Verdict:** false_positive\n\n"
    "**Confidence:** 0.96\n\n"
    "**Reasoning:**\n"
    "OTX enrichment shows no IOCs. Log correlation found only 2 events "
    "from a known scanner IP. This is clearly false_positive.\n\n"
    "**Self-Audit:**\n"
    "Could change if the scanner IP was compromised."
)

r = parse_agent_response(echoed_text)
print("TEST 1 — Echoed prompt")
print(f"  Verdict:    {r['verdict']}  (expected: false_positive)  {'PASS' if r['verdict'] == 'false_positive' else 'FAIL'}")
print(f"  Confidence: {r['confidence']}  (expected: 0.96)  {'PASS' if abs(r['confidence'] - 0.96) < 0.01 else 'FAIL'}")
print(f"  Self-audit: {'present' if r['self_audit'] else 'MISSING'}  {'PASS' if r['self_audit'] else 'FAIL'}")
print()

# ── Test 2: Simple true_positive response ────────────────────────────────
simple_tp = (
    "**Verdict:** true_positive\n\n"
    "**Confidence:** 0.85\n\n"
    "**Reasoning:**\n"
    "ATT&CK mapping identified T1110.001 brute force. "
    "Log correlation found 847 failed attempts. "
    "OTX enrichment shows the source IP is known malicious.\n\n"
    "**Self-Audit:**\n"
    "Could be wrong if this is an authorized penetration test.\n\n"
    "**Next Action:**\n"
    "Block the source IP immediately."
)

r2 = parse_agent_response(simple_tp)
print("TEST 2 — Simple true_positive")
print(f"  Verdict:    {r2['verdict']}  (expected: true_positive)  {'PASS' if r2['verdict'] == 'true_positive' else 'FAIL'}")
print(f"  Confidence: {r2['confidence']}  (expected: 0.85)  {'PASS' if abs(r2['confidence'] - 0.85) < 0.01 else 'FAIL'}")
print(f"  ATT&CK:     {r2['attack_technique']}  (expected: T1110.001)  {'PASS' if r2['attack_technique'] == 'T1110.001' else 'FAIL'}")
print(f"  Self-audit: {'present' if r2['self_audit'] else 'MISSING'}  {'PASS' if r2['self_audit'] else 'FAIL'}")
print()

# ── Test 3: Impact classification ────────────────────────────────────────
print("TEST 3 — Impact classification")

# Standard impact
impact1 = classify_impact("brute_force_login", {"hostname": "WS-001", "asset_tags": ["workstation"]})
print(f"  brute_force + workstation: {impact1}  (expected: standard)  {'PASS' if impact1 == 'standard' else 'FAIL'}")

# High impact: data_exfiltration
impact2 = classify_impact("data_exfiltration", {"hostname": "WS-001"})
print(f"  data_exfiltration: {impact2}  (expected: high_impact)  {'PASS' if impact2 == 'high_impact' else 'FAIL'}")

# High impact: critical asset tags
impact3 = classify_impact("brute_force_login", {"hostname": "SRV-DC-01", "asset_tags": ["critical-asset"]})
print(f"  brute_force + critical-asset: {impact3}  (expected: high_impact)  {'PASS' if impact3 == 'high_impact' else 'FAIL'}")

# High impact: DC hostname
impact4 = classify_impact("authentication_failure", {"hostname": "SRV-DC-01"})
print(f"  auth_failure + SRV-DC: {impact4}  (expected: high_impact)  {'PASS' if impact4 == 'high_impact' else 'FAIL'}")

# High impact: large data transfer
impact5 = classify_impact("port_scan", {"hostname": "WS-002", "bytes_sent": 500_000_000})
print(f"  port_scan + 500MB: {impact5}  (expected: high_impact)  {'PASS' if impact5 == 'high_impact' else 'FAIL'}")

print()

# ── Test 4: Empty response (safe defaults) ────────────────────────────────
r4 = parse_agent_response("")
print("TEST 4 — Empty response")
print(f"  Verdict:    {r4['verdict']}  (expected: true_positive)  {'PASS' if r4['verdict'] == 'true_positive' else 'FAIL'}")
print(f"  Confidence: {r4['confidence']}  (expected: 0.5)  {'PASS' if r4['confidence'] == 0.5 else 'FAIL'}")

print("\nAll parser unit tests complete.")
