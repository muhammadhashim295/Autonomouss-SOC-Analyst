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
- **Primary Agent (Alert Triage Agent):** initial investigation, basic response, documentation, step-by-step reasoning, self-auditing.
- **Secondary Agent (Deep Investigation Agent):** independently re-investigates the primary agent's output; executes standard remediation itself; escalates higher-impact decisions to a human analyst.
- **Firewall layer:** filters malicious/poisoned logs so no alert can be dismissed via log poisoning.
- **Per-agent IAM:** each agent has only the permissions it needs.

## Operating modes
A global toggle between:
1. **Agentic mode** — secondary agent acts autonomously on standard/low-impact actions; documents everything with clear explanation.
2. **Approval mode** — secondary agent escalates standard-impact decisions to a human analyst with evidence and a reasoned suggestion; analyst approves, redirects, or acts themselves.

**Hard rule, both modes:** high-impact actions always require human approval. Mode never overrides this.

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
- Fully functional system: real backend, real API integrations (OTX, Gemini), real database (Supabase), not just a workflow demo.
- Two distinct, independently reasoning agents actually running.
- Demonstrable, enforced IAM scoping per agent (not just prompt-level).
- A real, testable log-poisoning firewall (proven against crafted test cases and continuously via Gemini-generated live feed with ~15% poison ratio).
- A working human-in-the-loop escalation and override flow, with the override visibly updating agent memory for future cases.
- A clear demonstration that high-impact actions are always human-gated, in both modes.
- A "Generate Live Feed" button that triggers real-time, Gemini-generated alert traffic to demonstrate continuous autonomous operation.

## Explicit non-goals (MVP scope)
- No fine-tuned/self-hosted model for the demo (LLM API used; fine-tuning is roadmap, not MVP).
- No real production SIEM/EDR integration (GUIDE dataset replay + Gemini-generated live feed are the alert sources).
- No real infrastructure execution for response actions (simulated/logged only).
- No high-volume concurrency requirement (2-3 parallel sessions is sufficient to prove the architecture).

## Team
Hashim (lead) and Huzaifa (teammate).

## Timeline
7 days total to build and demo.
