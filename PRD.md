# PRD — Autonomous SOC Analyst Framework

## Project
Pakistan's first compliance-friendly, explainable Autonomous SOC Analyst framework, built for the Alibaba Cloud AI Hackathon Pakistan 2026 (Alkhidmat Foundation / Bano Qabil, theme: "AI for Pakistan's Future").

## Problem
Most autonomous security tools optimize for speed and coverage but treat their reasoning as a black box. This is a hard sell for regulated sectors like banking, where every decision must be explainable and auditable. Analysts don't trust black-box AI verdicts and end up re-investigating everything anyway, killing the time savings automation was supposed to deliver.

## Target user / persona
A bank's (or other regulated organization's) SOC team — chosen given the team's background with Raqami Islamic Digital Bank and the compliance angle. Broader applicability: any under-resourced SOC that can't staff 24/7 human triage.

## Core idea
A two-tier multi-agent system that triages, investigates, and responds to security alerts with full explainability and a self-checking audit structure, so no single AI decision is ever a black box.

## Architecture summary (see architecture.md for full detail)
- **Primary Agent (Alert Triage Agent) — Groq:** initial investigation, basic response, documentation, step-by-step reasoning, self-auditing.
- **Secondary Agent (Deep Investigation Agent) — Groq:** independently re-investigates the primary agent's output with its own prompt; executes standard remediation itself; escalates high-impact decisions to a human analyst.
- **Firewall layer:** pre-execution check for log-poisoning and adversarial directives. If flagged, escalates DIRECTLY to human analyst without agent investigation.
- **Live Alert Feed — Cloudflare Workers AI:** generates real-time synthetic alert traffic with realistic payloads and injected poison scenarios.
- **Per-agent IAM:** each agent has only the permissions it needs.

## Fixed operational flow (no mode toggle)
The system operates on an enforced, deterministic flow without an agentic/approval mode toggle:
1. **Alert arrives → Firewall check**:
   - If flagged: escalates DIRECTLY to human analyst (Primary and Secondary agents are bypassed entirely).
   - If clean: passes to Primary Agent.
2. **Primary Agent (Groq)**:
   - `false_positive` → close + document case (no Secondary handoff).
   - `true_positive` → hand off to Secondary Agent.
3. **Secondary Agent (Groq)**:
   - `false_positive` (disagrees with primary) → close + document case.
   - `true_positive` (agrees with primary) → check impact level:
     - **Standard / low-impact action**: Secondary Agent executes autonomously and documents reasoning (ALWAYS autonomous).
     - **High-impact action**: ALWAYS escalated to human analyst with evidence, reasoning, and suggested action.

## Learning
The system "learns" via retrieval-augmented case memory, not model retraining:
- Every investigation (evidence, verdict, outcome) is written to a shared case-memory store.
- Analyst corrections/overrides are written as distinct, higher-weight correction records.
- Both agents retrieve similar past cases before acting.
- Every memory write is versioned — this doubles as the audit trail.

## Investigation signals (used by both agents)
- Log/event correlation
- IOC enrichment (AlienVault OTX)
- ATT&CK technique mapping
- Basic behavioral-deviation heuristic

## Response actions (simulated for MVP, real logging/documentation)
Standard: block IOC, open ticket, tag/flag for review.
High-impact (always human-gated): isolate host, disable/lock account, any action on a critical asset, any multi-asset action.

## Success criteria for the hackathon submission
- Fully functional system: real backend, real API integrations (OTX, Groq for both agents, Cloudflare Workers AI for alert generator), real database (Supabase), not just a workflow demo.
- Two distinct, independently reasoning agents actually running on Groq with separate roles and prompts.
- Demonstrable, enforced IAM scoping per agent (not just prompt-level).
- A real, testable log-poisoning firewall that directly escalates flagged alerts to human analysts without running agent investigation.
- A working human-in-the-loop escalation and override flow, with the override visibly updating agent memory for future cases.
- Enforced fixed flow: standard actions execute autonomously; high-impact actions always gate on human approval.
- A "Generate Live Feed" button that triggers real-time, Cloudflare Workers AI-generated alert traffic to demonstrate continuous autonomous operation.

## Explicit non-goals (MVP scope)
- No fine-tuned/self-hosted model for the demo (LLM API used; fine-tuning is roadmap, not MVP).
- No real production SIEM/EDR integration (GUIDE dataset replay + Cloudflare Workers AI-generated live feed are the alert sources).
- No real infrastructure execution for response actions (simulated/logged only).
- No high-volume concurrency requirement (2-3 parallel sessions is sufficient to prove the architecture).

## Team
Hashim (lead) and Huzaifa (teammate).

## Timeline
7 days total to build and demo.
