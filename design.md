# Design — Autonomous SOC Analyst Framework

## Supabase schema (dashboard-facing data)

### `alerts`
- `id` (uuid, pk)
- `source_alert_id` (text) — original ID from GUIDE dataset or feed
- `alert_type` (text)
- `raw_payload` (jsonb)
- `received_at` (timestamp)
- `status` (enum: pending, in_review, closed)

### `cases`
- `id` (uuid, pk)
- `alert_id` (fk -> alerts)
- `mode` (enum: agentic, approval)
- `primary_verdict` (enum: false_positive, true_positive)
- `primary_confidence` (float)
- `secondary_verdict` (enum: false_positive, true_positive, agree, disagree)
- `attack_technique` (text, nullable)
- `impact_level` (enum: standard, high_impact)
- `action_taken` (text, nullable)
- `action_status` (enum: none, executed, escalated, awaiting_approval)
- `closed_at` (timestamp, nullable)
- `qoder_memory_record_id` (text) — pointer back to the full case record in the Supabase `memory_records` table (legacy column name; the store is Supabase, not an external agent platform)
- `primary_provider` (text, nullable) — provider that ran the Primary Alert Triage Agent (`groq`); added in migration 005
- `secondary_provider` (text, nullable) — provider that ran the Secondary Deep Investigation Agent (`groq`); NULL until the secondary runs; added in migration 005

### `analyst_overrides`
- `id` (uuid, pk)
- `case_id` (fk -> cases)
- `original_suggestion` (text)
- `analyst_decision` (enum: approved, redirected, self_acted)
- `analyst_action` (text, nullable)
- `analyst_reasoning` (text, nullable)
- `created_at` (timestamp)

### `firewall_flags`
- `id` (uuid, pk)
- `alert_id` (fk -> alerts)
- `flag_reason` (text)
- `raw_snippet` (text) — the offending content, sanitized for storage
- `created_at` (timestamp)

## Case Memory Store (Supabase `memory_records`) — case record schema
Each investigation writes a structured record:
- `alert_id`, `timestamp`, `alert_type`
- `evidence_gathered` — log correlation results, OTX IOC matches, behavioral deviation flags
- `attack_technique` — mapped ATT&CK ID
- `verdict` — FP or TP, with confidence
- `reasoning` — plain-language explanation
- `response_taken` — action + outcome (if any)
- `analyst_correction` (nullable) — what changed, and why, if overridden
- `record_type` — `case` or `correction` (corrections are retrieved with higher priority/weight for similar future alerts)

## Impact classification (enforced logic, not just prompt instruction)

**Standard / low-impact** (Secondary Agent executes autonomously):
- Block a single known-malicious IP/domain (OTX-flagged IOC)
- Open a ticket/case
- Flag/tag an alert for review
- Enrich and document only, no system change
- **Execution rule:** ALWAYS autonomous, documented with full reasoning. Zero mode toggle.

**High-impact** (always human-gated):
- Isolate a host from the network
- Disable/lock a user account
- Any action touching a tagged "critical asset" (config-driven list — e.g. domain controllers, prod DB servers, exec accounts)
- Any action affecting more than one asset at once
- **Execution rule:** ALWAYS pauses in `awaiting_approval` and escalates to human analyst with evidence, reasoning, and suggested action.

This is implemented as a deterministic function in `app/services/actions.py` called before acting — a lookup against a config list, not a judgment call left to the LLM's discretion.

## Frontend screens

### Alert queue / live feed queue
Real-time streaming list of incoming alerts with status badges (pending, in_review, closed), firewall flags indicator, and active stream state.

### Case detail
- Primary agent's full reasoning chain (evidence, technique, verdict, confidence, self-audit)
- Secondary agent's independent re-investigation and cross-check verdict
- Firewall flags (if any) with raw snippet
- Action outcome / status

### Escalation / approval modal
Shown for high-impact cases and alerts flagged by the firewall:
- Evidence summary & firewall flag reasons
- Agent reasoning chain (if investigation ran)
- Suggested action + reasoning
- Past similar cases (retrieved via RAG memory)
- Controls: Approve / Redirect (with text input) / Self-act (with text input)

### Memory-update indicator
When an analyst override is saved, a visible confirmation that the correction was written to memory — this is the live demo moment proving the learning loop.

## Demo data
GUIDE dataset fallback alerts (kept in `app/data/sample_alerts.json` for fallback/seed injection):
1. **Clean false positive (GUIDE-FP-001):** Primary investigates, closes as FP; no Secondary Agent involvement.
2. **Clear true positive, standard action (GUIDE-TP-001):** Primary TP → Secondary TP → low-impact action (`block_ip`) executed autonomously with full documentation.
3. **True positive with analyst correction (GUIDE-TP-002):** Escalated / reviewed case overridden by analyst; correction written to memory.
4. **Repeat/similar alert (GUIDE-TP-002-B):** Proves RAG recall of the prior analyst correction.
5. **High-impact scenario (GUIDE-HI-001):** Primary TP → Secondary TP → classifies as high-impact (`isolate_host`) → ALWAYS human-gated (`awaiting_approval`).
6. **Poisoned log scenario (GUIDE-POISON-001):** Pre-execution firewall flags prompt injection → escalates DIRECTLY to human analyst without running Primary/Secondary agents.

## Poisoned log test cases
Constructed by the team, not from the GUIDE dataset — should include a few known indirect-prompt-injection patterns embedded in log fields (e.g. "ignore previous instructions", role-play/system-prompt-mimicking text, unusual encoding) to prove the firewall middleware catches them before either agent processes the alert.

## Live feed generation (Cloudflare Workers AI-backed)

### Purpose
Produce a continuous stream of realistic, varied security alerts for demo/testing purposes. Supplements the 6 scripted GUIDE demo beats with additive background traffic. The firewall runs on every generated alert — no bypass.

### Backend API

**`POST /alerts/generate/start`**
Starts a background generation run. Does not block the request.
- **Params (all optional):**
  - `duration_seconds` (int, default 120) — how long the run lasts
  - `interval_seconds` (int, default 3) — seconds between each generated alert (stable default within the 2-3 s window)
  - `poison_ratio` (float, default 0.15) — probability that any given generated alert contains a prompt-injection/log-poisoning payload (~1 in 7)
- **Behavior:**
  - Runs as a FastAPI background task (asyncio)
  - On each interval tick, calls Cloudflare Workers AI to generate one alert matching the `alerts` table schema (`source_alert_id`, `alert_type`, `raw_payload`)
  - POSTs the generated alert through the existing `POST /alerts/` ingestion pipeline — firewall runs on every one
  - Stops automatically after `duration_seconds` elapses
  - Does NOT touch or interfere with the 6 scripted GUIDE demo alerts
- **Response:** `{ "status": "started", "run_id": "...", "duration_seconds": 120, "interval_seconds": 3, "poison_ratio": 0.15, "estimated_alerts": 40 }`

**`GET /alerts/generate/status`**
Returns the current state of the generation run.
- **Response (active):** `{ "status": "running", "run_id": "...", "started_at": "...", "alerts_generated": 12, "alerts_remaining": 12, "estimated_seconds_left": 60 }`
- **Response (idle):** `{ "status": "idle" }`

**`POST /alerts/generate/stop`**
Cancels an in-progress generation run early.
- **Response:** `{ "status": "stopped", "alerts_generated": 8 }`

### Cloudflare Workers AI alert generation spec
Each call to Cloudflare Workers AI produces one alert with:
- `source_alert_id`: `LIVE-<timestamp>-<random>` to distinguish from GUIDE alerts
- `alert_type`: one of — `brute_force_login`, `port_scan`, `suspicious_process_execution`, `data_exfiltration`, `authentication_failure`, `malware_detected`, `phishing_email`, `dns_anomaly`, `lateral_movement`, `privilege_escalation`
- `raw_payload`: realistic fields matching the alert type (IPs, ports, timestamps, log entries, hostnames, usernames, etc.)
- Poison variants (when `poison_ratio` triggers): embed prompt-injection patterns in log fields — instruction overrides, system-tag mimicry, role-play directives, verdict manipulation

### Frontend (deferred to frontend phase)
- "Generate Live Feed" button in the dashboard near the alert queue
- On click: calls `POST /alerts/generate/start`, button shows active/running state (disabled + "Generating..." + countdown)
- New alerts appear in the alert queue in near-real-time via polling (upgradeable to SSE later)
- Button reverts to normal when the run completes or is stopped
