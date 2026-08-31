"""Quick check: secondary verdict + impact level parsing."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.services.investigation import parse_agent_response

t = (
    "**Secondary Verdict:** agree\n"
    "**Confidence:** 0.93\n"
    "**Reasoning:** My evidence shows...\n"
    "**Impact Level:** standard\n"
    "**Recommended Action:** Block the IP\n"
    "**Self-Audit:** Could be wrong if..."
)
r = parse_agent_response(t)
print(f"secondary_verdict = {r['secondary_verdict']}")
print(f"impact_level      = {r['impact_level']}")
print(f"confidence        = {r['confidence']}")

t2 = (
    "**Secondary Verdict:** disagree\n"
    "**Confidence:** 0.71\n"
    "**Reasoning:** The primary overlooked...\n"
    "**Impact Level:** high_impact\n"
)
r2 = parse_agent_response(t2)
print(f"\nsecondary_verdict = {r2['secondary_verdict']}")
print(f"impact_level      = {r2['impact_level']}")
print(f"confidence        = {r2['confidence']}")
