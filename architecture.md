# Architecture — Autonomous SOC Analyst Framework

## Tech stack
- **Frontend:** React + Vite + Tailwind
- **Backend:** Python + FastAPI (async)
- **Agent orchestration:** two AI providers system-wide, one for reasoning and one for alert generation:
  - **Groq:** ALL agent reasoning — both Primary Alert Triage Agent and Secondary Deep Investigation Agent run on Groq with distinct role prompts and isolated sessions.
  - **Cloudflare Workers AI:** live alert generation (synthetic telemetry and log-poisoning injection).
  The backend owns the investigation pipeline, shared agent prompts, deterministic execution gates, and SSE event vocabulary.
- **Dashboard database:** Supabase (Postgres) — free tier
- **Agent memory / audit trail:** Supabase `memory_records` table (source of truth for case history, learning, and audit). The `cases.qoder_memory_record_id` column is the (legacy-named) pointer to a memory record — the name is retained for compatibility, but the store is Supabase, not any external agent platform.
- **Real-time updates:** Server-Sent Events (SSE) emitted by the backend's own pipeline code — token-by-token streaming relayed directly to the frontend.
- **Auth (if needed):** Supabase Auth
- **Hosting:** Vercel (frontend), Railway or Render (backend)
- **Threat intel:** AlienVault OTX integration, logic folded into the FastAPI backend

## End-to-end flow

### 1. Ingestion
Alerts arrive from three sources:
- **Live feed generation (Cloudflare Workers AI)** — primary/default alert source for the demo. A background worker pool calls Cloudflare Workers AI to generate realistic, varied security alerts on a timed interval (default every 3 s; run duration default 120 s). A configurable poison ratio (~15%) injects prompt-injection/log-poisoning payloads to continuously exercise the firewall.
- **GUIDE dataset replay** — 6 scripted demo beats (FP-001, TP-001, TP-002, TP-002-B, HI-001, POISON-001), kept available for manual on-demand injection as fallback/seed options.
- **Manual / API** — direct POST to the ingestion endpoint for ad-hoc testing.

Each alert is inserted into the `alerts` table and gets a unique `id`.

### 2. Firewall (log-poisoning defense & direct escalation)
Before any agent sees the alert/logs, a pre-execution heuristic firewall layer checks for:
- Malformed structure
- Suspicious embedded instructions (prompt-injection patterns — "ignore previous instructions", role-play markers, unusual encoding)
- Adversarial jailbreaks and exfiltration instructions

**Fixed escalation behavior on flag:**
If the firewall flags the alert, it logs to `firewall_flags`, marks the alert `in_review`, and escalates **DIRECTLY** to human analyst review (with flag reasons cited). The alert does **NOT** run Primary or Secondary agent investigation.

### 3. Primary Agent — Alert Triage Agent (Groq)
For clean alerts passing the firewall, the Primary Agent runs on **Groq** via its Chat Completions API with SSE streaming.
- **IAM:** read-only on logs/IOC lookups; write access only to its own case documentation; no execution permissions.
- **Investigation skills:** OTX enrichment, ATT&CK mapping, log/event correlation, behavioral-deviation heuristic.
- **Process:** retrieves similar past cases from memory store → runs investigation skills → forms verdict (FP/TP) with confidence and evidence-cited reasoning → self-audits ("what could make this verdict wrong?") → documents.
- **Verdict routing:**
  - `false_positive` → case is closed and documented immediately; no Secondary Agent involvement.
  - `true_positive` → hands off to Secondary Agent.

### 4. Secondary Agent — Deep Investigation Agent (Groq)
The Secondary Agent also runs on **Groq**, using its own independent system prompt per `agentrules.md`. It independently re-investigates the Primary Agent's case (re-derives evidence with a fresh skill run, rather than blindly trusting the primary's conclusion).
- **IAM:** read access to primary's output and logs; write access to case memory; execution permissions scoped only to standard/low-impact actions (never high-impact).
- **Process:** receives primary findings, re-runs skills, evaluates evidence, and outputs its independent verdict.
- **Disagreement handling:** if Secondary finds `false_positive` (disagreeing with Primary), the case is closed and documented.

### 5. Fixed Action Flow (No Mode Toggle)
The agentic/approval mode toggle is eliminated in favor of an enforced, deterministic flow:
- **Standard / low-impact actions:** When Primary and Secondary agree on `true_positive`, the Secondary Agent executes standard actions itself (simulated block_ip, open_ticket, tag/flag) and documents full reasoning — **ALWAYS autonomous**, with zero mode checks.
- **High-impact actions:** (isolate_host, disable_account, multi-asset remediation) **ALWAYS escalate** to a human analyst with evidence, reasoning, and suggested action (`awaiting_approval`). This human gate is absolute and hardcoded in `app/services/actions.py`.

### 6. Human escalation (high-impact actions or firewall-flagged alerts)
Analyst sees (via dashboard): alert details, firewall flag reasons (if flagged directly) or both agents' reasoning chains, evidence trail, ATT&CK mapping, confidence, suggested action, and relevant past similar cases. Analyst can:
- **Approve** → system executes the suggested action.
- **Redirect** → analyst specifies an alternative action.
- **Self-act** → analyst handles remediation out-of-band.
Outcome + analyst's stated reasoning is written back to the case record.

### 7. Memory write-back (learning)
At case close:
- A structured case record is written to the Supabase `memory_records` table.
- Analyst corrections/overrides are written as distinct, higher-weight correction records.
- Every memory write is versioned in Supabase — providing a complete audit trail.

### 8. Supabase sync
After case close or escalation, a summary row is written to Supabase (`cases` table): case_id, alert_type, verdict, impact_level, action_status, action_taken, timestamp, analyst_override (if any), firewall_flags reference.

### 9. Frontend
- Alert queue / live stream queue (Supabase-backed)
- Case detail view: live streaming reasoning chains, evidence, ATT&CK mapping
- Escalation modal: evidence + suggested action + approve/redirect/self-act controls
- Live "memory updated" indicator when a correction is saved
- **Generate Live Feed controls** — controls Cloudflare Workers AI-backed live feed; displays real-time cadence and counter statistics

## Concurrency model
Each alert gets its own isolated provider sessions on Groq (Primary session, and Secondary session if true positive). Multiple alerts are handled concurrently, all reading/writing to the same shared Supabase case memory.

## IAM enforcement note
IAM scoping is enforced in backend application code — not merely described in an agent's prompt. The agents are reasoning calls that hold no infrastructure credentials; every response action passes through the deterministic impact-classification function and the high-impact human-gating rule in `app/services/actions.py`, which an agent cannot bypass regardless of its text output. Per-role separation is real: the Primary Agent (Groq) has no execution path, and the Secondary Agent (Groq) may only trigger standard/low-impact actions. Flagged alerts bypass both agents entirely.
