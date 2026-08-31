# Autonomous SOC Analyst Framework

A two-tier multi-agent system that triages, investigates, and responds to security alerts with full explainability and a self-checking audit structure, so no single AI decision is ever a black box. Built for Pakistan's regulated sectors (starting with banking), the framework pairs a Primary Alert Triage Agent with an independent Secondary Deep Investigation Agent, enforcing per-agent IAM scoping, a log-poisoning firewall, and a human-in-the-loop escalation flow that ensures high-impact actions always require analyst approval.

## Folder Structure

```
.
├── backend/                # Python + FastAPI (async) backend
│   ├── migrations/         # Supabase SQL migration files
│   └── .env.example        # Environment variable template
├── frontend/               # React + Vite + Tailwind dashboard
├── PRD.md                  # Product requirements and scope
├── architecture.md         # System architecture and end-to-end flow
├── design.md               # Database schema, frontend screens, demo plan
├── agentrules.md           # Agent behavioral rules and IAM scoping
├── phases.md               # 7-day build plan (20 steps)
├── .gitignore
└── README.md
```

## Documentation

- [PRD](PRD.md) — Product requirements and scope
- [Architecture](architecture.md) — System architecture and end-to-end flow
- [Design](design.md) — Database schema, frontend screens, demo data plan
- [Agent Rules](agentrules.md) — Behavioral rules and IAM scoping per agent
- [Phases](phases.md) — 7-day build plan (20 steps)
