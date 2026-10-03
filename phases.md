# Phases — Build Plan (7 days)

Each step is scoped to be independently buildable and verifiable before moving to the next. Work through them one at a time, confirming each verify condition before proceeding.

**1. Repo + Supabase schema**
Monorepo (`/backend`, `/frontend`). Tables: `alerts`, `cases`, `analyst_overrides`, `firewall_flags`.
Verify: manually insert/query a row from each table.

**2. FastAPI skeleton + Supabase connection**
Basic FastAPI app, Supabase client wired in, health-check endpoint.
Verify: FastAPI can read/write to Supabase.

**3. Alert ingestion endpoint + GUIDE dataset replay**
Endpoint to accept an alert; script to feed pre-selected GUIDE dataset alerts on demand or timed.
Verify: alerts land correctly in `alerts` table.

**3b. Live feed generation (Cloudflare Workers AI-backed)**
Background task that calls Cloudflare Workers AI to generate realistic, varied security alerts on a timed interval (default: 120 s duration, 3 s interval). A configurable poison ratio (~15%) injects prompt-injection payloads to continuously exercise the firewall. Endpoints: `POST /alerts/generate/start`, `GET /alerts/generate/status`, `POST /alerts/generate/stop`. Generated alerts flow through the existing ingestion pipeline — firewall runs on every one. Does not interfere with the 6 scripted GUIDE demo alerts.
Verify: start a generation run, confirm alerts appear in `alerts` table with `LIVE-*` source IDs; confirm poison alerts are flagged by the firewall; confirm stop cancels early.
*Frontend button deferred to Phase 15b.*

**4. Log-poisoning firewall (middleware & direct escalation)**
Sanitization/validation layer between ingestion and agents; flags/rejects malformed or injection-pattern content; writes to `firewall_flags`.
**Fixed behavior:** If flagged, the alert escalates DIRECTLY to a human analyst in `awaiting_approval` without running Primary or Secondary agent investigation.
Verify: normal alert passes clean to Primary Agent; a crafted poisoned-log test case (e.g. `GUIDE-POISON-001`) is caught, flagged, and directly escalated to human review without AI agents.

**5. Primary Agent setup (Groq)**
Wire the Primary Alert Triage Agent to Groq's OpenAI-compatible Chat Completions API (streaming). Load the OTX key for IOC enrichment; scope the agent read-only on logs/IOC lookups + documentation-write, with no execution path.
Verify: a virtual session is created and the agent streams an evidence-cited verdict for a manually passed alert.

**6. Primary agent's investigation skills (one at a time)**
6a. OTX enrichment (port existing integrator logic)
6b. ATT&CK mapping
6c. Log correlation
6d. Behavioral-deviation heuristic
Verify each individually on a known test alert.

**7. Primary agent full investigation flow**
Wire skills together → verdict + confidence + reasoning + self-audit statement.
- If false_positive: close case and document immediately (no Secondary handoff).
- If true_positive: hand off to Secondary Agent.
Verify: consistent, evidence-cited output across test alerts.

**8. Secondary Agent setup (Groq)**
Wire the Secondary Deep Investigation Agent to Groq using an independent auditor role prompt and separate virtual session. Execution is scoped to standard/low-impact actions only (no high-impact permissions).
Verify: a virtual session is created and the agent can read the primary's output and re-investigate independently via Groq.

**9. Secondary agent's independent re-investigation**
Reuses Step 6 skills to cross-check rather than trust primary's verdict outright.
Verify: secondary agent independently re-examines evidence and can disagree on ambiguous test cases.

**10. Impact classification + standard-action execution**
Config/skill defining standard vs. high-impact actions in `app/services/actions.py`:
- Standard / low-impact: executed autonomously, documented with full reasoning (ALWAYS autonomous).
- High-impact: ALWAYS pauses for human analyst approval (`awaiting_approval`).
Verify: standard TP executes autonomously; high-impact TP pauses for analyst approval.

**11. Case memory + retrieval + learning (Supabase)**
Use the Supabase `memory_records` table as the shared case memory for both agents. Write structured case records on close; retrieve similar past cases before new investigations.
Verify: two similar alerts in sequence — second references the first.

**12. Fixed operational flow (mode toggle removed)**
Enforce the fixed flow pipeline without the former agentic/approval mode toggle:
1. Alert arrives → firewall check.
2. Firewall flags the alert → escalate DIRECTLY to human analyst without agent investigation.
3. Clean alert → Primary Agent investigates (Groq). If FP → close + document. If TP → hand off to Secondary.
4. Secondary Agent investigates (Groq). If FP → close + document. If TP:
   - low/standard impact → Secondary executes action autonomously (ALWAYS autonomous).
   - high impact → ALWAYS escalate to human analyst.
Verify all 4 scenarios.

**13. Analyst decision handling + correction memory**
Endpoint/flow for analyst to approve, redirect, or self-act. Overrides written as distinct correction records.
Verify: override an alert, replay a similar one, confirm the agent's next suggestion reflects the correction.

**14. SSE streaming from backend**
The backend emits its own provider-driven SSE events (`investigation_started`, `agent_started`, `agent_delta`, `agent_complete`, `action_decided`, `investigation_complete`) so agent reasoning appears live as tokens stream from Groq.
Verify: reasoning appears progressively in a basic test client.

**15. Frontend: alert queue + case detail**
React dashboard — alert/case list, case detail with both agents' reasoning chains, firewall flags, evidence.

**15b. Frontend: Generate Live Feed button**
"Generate Live Feed" button in the dashboard near the alert queue. On click: calls `POST /alerts/generate/start` (default 120 s, 3 s interval, 15% poison ratio). Button shows active/running state (disabled + "Generating..." + countdown) for the duration, then reverts. New alerts appear in the alert queue in near-real-time via polling (upgradeable to SSE later). Wired to Phase 3b backend endpoints.

**16. Frontend: escalation/approval screen**
Evidence + suggested action + approve/redirect/self-act controls, wired to Step 13.

**17. Frontend: memory-update indicator + fixed flow UI**
Mode toggle removed; clean UI shows autonomous dual-agent pipeline status and visible confirmation when a correction is written to memory.

**18. Deploy**
Frontend to Vercel, backend to Railway/Render, environment variables/secrets configured.

**19. Demo data curation + dry run**
Finalize the 6 demo beats (see design.md); full timed run-through.

**20. IAM/audit documentation**
One-page write-up of each agent's permissions and why, ready for organizer questions.

## Suggested split
Roughly 3 steps/day across 7 days if split in parallel — e.g. Hashim on agents/backend (Steps 1-14, 20), Huzaifa on frontend/Supabase (Steps 1-3, 15-19), converging at Steps 14-17.

## Hard internal cutoff
Agree on a cutoff day (e.g. day 5-6) after which no new scope is added — remaining time goes to debugging and demo prep only.
