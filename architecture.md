# Architecture — Autonomous SOC Analyst Framework

## Tech stack
- **Frontend:** React + Vite + Tailwind
- **Backend:** Python + FastAPI (async)
- **Agent orchestration:** Qoder Cloud Agents API (agents, sessions, environments, skills, vaults, memory stores), called from the FastAPI backend
- **Dashboard database:** Supabase (Postgres) — free tier
- **Agent memory / audit trail:** Qoder Memory Store (source of truth for case history, learning, and audit)
- **Real-time updates:** Server-Sent Events (SSE), backend relays live Qoder session events to frontend
- **Auth (if needed):** Supabase Auth
- **Hosting:** Vercel (frontend), Railway or Render (backend)
- **Threat intel:** existing Flask-based OTX integrator, logic folded into the FastAPI backend

## End-to-end flow

### 1. Ingestion
Alerts arrive from three sources:
- **GUIDE dataset replay** — 6 scripted demo beats (FP-001, TP-001, TP-002, TP-002-B, HI-001, POISON-001), seeded on demand or timed.
- **Live feed generation (Gemini)** — a background task calls Gemini to generate realistic, varied security alerts on a timed interval (~every 5 s for 120 s). A configurable poison ratio (~15%) injects prompt-injection/log-poisoning payloads to continuously exercise the firewall. Generated alerts flow through the same ingestion pipeline and firewall as manual alerts — no separate path.
- **Manual / API** — direct POST to the ingestion endpoint for ad-hoc testing.

Each alert is inserted into the `alerts` table and gets a unique `id`.

### 2. Firewall (log-poisoning defense)
Before any agent sees the alert/logs, a sanitization/validation middleware layer checks for:
- Malformed structure
- Suspicious embedded instructions (prompt-injection patterns — "ignore previous instructions", role-play markers, unusual encoding)
Flagged/rejected entries are logged to `firewall_flags` in Supabase. This is real enforced code, not a prompt-level instruction.

### 3. Primary Agent — Alert Triage Agent
A new Qoder Session is created per alert, bound to the Primary Agent definition.
- **IAM:** read-only on logs/IOC lookups; write access only to its own case documentation; no execution permissions.
- **Investigation skills:** OTX enrichment, ATT&CK mapping, log/event correlation, behavioral-deviation heuristic.
- **Process:** retrieves similar past cases from memory store → runs investigation skills → forms verdict (FP/TP) with confidence and evidence-cited reasoning → self-audits ("what could make this verdict wrong?") → documents.
- If FP: closes and documents. If TP: proceeds to Secondary Agent.

### 4. Secondary Agent — Deep Investigation Agent
Independently re-investigates the Primary Agent's case (re-derives evidence, does not just trust the primary's conclusion — reuses the same skill set for cross-checking).
- **IAM:** read access to primary's output and logs; write access to case memory; execution permissions scoped only to standard/low-impact actions (never high-impact).
- **Impact classification check:** before acting, checks the alert/action against the impact-classification rule (a real, inspectable Skill/config — see design.md).
- **Standard/low-impact actions:** block known-malicious IOC, open ticket, tag/flag for review.
- **High-impact actions:** isolate host, disable/lock account, any action on a critical asset, any multi-asset action.

### 5. Mode branch (applies to Secondary Agent's standard-action decisions only)
- **Agentic mode:** secondary agent executes standard actions itself, fully documented.
- **Approval mode:** secondary agent escalates standard actions to the analyst with evidence + reasoning + suggested action; session pauses.
- **Regardless of mode:** high-impact actions always escalate to a human analyst. This rule is not overridable by the mode toggle.

### 6. Human escalation (approval mode, or any high-impact case)
Analyst sees (via dashboard): both agents' reasoning, evidence trail, ATT&CK mapping, confidence, suggested action, relevant past similar cases. Analyst either:
- Approves → agent executes the suggested action.
- Redirects → tells the agent to do something else.
- Self-acts → analyst handles it directly.
Outcome + analyst's stated reasoning is written back to the session.

### 7. Memory write-back (learning)
At case close (either mode):
- A structured case record is written to the Qoder Memory Store (fields: see design.md).
- Analyst corrections are written as a distinct, higher-weight correction record.
- Every memory write is versioned automatically by Qoder — this is the audit trail.

### 8. Supabase sync
After session close, a summary row is written to Supabase (`cases` table): case_id, alert_type, verdict, mode, action_taken, timestamp, analyst_override (if any), firewall_flags reference. This is what the dashboard queries — it does not need to parse memory-store documents directly.

### 9. Frontend
- Alert queue / case list (Supabase-backed)
- Case detail view: both agents' full reasoning chains, evidence, ATT&CK mapping
- Escalation screen: evidence + suggested action + approve/redirect/self-act controls
- Mode toggle (agentic / approval)
- Live "memory updated" indicator when a correction is saved (key demo moment)
- **Generate Live Feed button** — triggers Gemini-backed alert generation; shows active/countdown state while running; new alerts appear in the queue in near-real-time via polling

## Concurrency model
Each alert gets its own Qoder Session (Primary + Secondary agent sessions). Multiple alerts are handled via multiple concurrent sessions, all reading/writing to the same shared Memory Store — so a correction learned in one session is visible to a session running concurrently on a related alert. MVP target: 2-3 parallel sessions is sufficient to prove the architecture; no high-throughput requirement.

## IAM enforcement note
IAM scoping must be enforced at the Vault/credential level in Qoder, not just described in the agent's system prompt — a prompt-level restriction is not real IAM and should not be relied on as the sole control.
