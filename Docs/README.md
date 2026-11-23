# WellCast Documentation Index

Welcome to the **WellCast: Groundwater Depletion Forecaster** documentation hub.  
This directory (along with root `README.md`, `DATA_SOURCES.md`, and `ai_logs/`) contains the complete operational, architectural, machine learning, cloud infrastructure, and hackathon submission blueprint for building WellCast between **24 Nov and 30 Nov 2026** for the **Campus to Cloud Hackathon sponsored by AWS (Techfest 2026-27, IIT Bombay)**.

---

## Quick Navigation & Reading Order

If you are starting a new build session (human developer or AI coding assistant), follow this reading order:

| Order | Document | Purpose | When to Use |
|---|---|---|---|
| 1 | [`../ai_logs/SESSION_INDEX.md`](../ai_logs/SESSION_INDEX.md) | Chronological log of completed sessions and latest handoff | **Start and end of every session** |
| 2 | [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) | Original high-level 10-phase roadmap, fallbacks, and guardrails | Strategic baseline and scope check |
| 3 | [`EXECUTION_PLAN.md`](./EXECUTION_PLAN.md) | Operational day-by-day runbook, Task IDs (`T0.1`–`T10.4`), decision gates, critical path, and DoD | **Primary daily execution tracker** |
| 4 | [`WORKFLOW.md`](./WORKFLOW.md) | Step-by-step Git, AI session, Data, ML, Backend, Frontend, and Incident workflows | Before executing any phase or PR |
| 5 | [`../DATA_SOURCES.md`](../DATA_SOURCES.md) | Verified dataset registry, licences, attribution, and missing-data rules | Phase 0, Phase 1, Phase 8, Phase 9 |
| 6 | [`ARCHITECTURE_AND_DATA_SPEC.md`](./ARCHITECTURE_AND_DATA_SPEC.md) | S3 lake layout, schemas, block ID standard, Athena SQL, and anti-leakage rules | Phase 1, Phase 2, Phase 4 |
| 7 | [`ML_SPEC.md`](./ML_SPEC.md) | Feature catalog, time-split validation, Baseline/XGBoost/Quantiles, risk calibration, scenarios, SageMaker | Phase 2, Phase 3, Phase 4 |
| 8 | [`API_AND_FRONTEND_SPEC.md`](./API_AND_FRONTEND_SPEC.md) | S3 static JSON contracts, 5 REST endpoints, 7-step React/Leaflet UI spec, EN/HI/MR i18n | Phase 4, Phase 5, Phase 6 |
| 9 | [`AWS_INFRA_AND_SECURITY.md`](./AWS_INFRA_AND_SECURITY.md) | AWS setup, least-privilege IAM JSON policies, Budgets, CloudWatch, CloudFront OAC, QuickSight | Phase 0, Phase 1, Phase 5–8 |
| 10 | [`TESTING_AND_QA_CHECKLIST.md`](./TESTING_AND_QA_CHECKLIST.md) | Verification suites, hardening audit, submission checklist, video shot list, Demo Day Q&A | Phase 8, Phase 9, Phase 10, Demo Day |
| 11 | [`idea-brief.md`](./idea-brief.md) | Hackathon submission Idea Brief (structured draft) | Phase 9 submission package |
| 12 | [`build-summary.md`](./build-summary.md) | Hackathon submission AWS Build Summary (structured draft) | Phase 9 submission package |

---

## Documentation Ownership by Role

| Role | Primary Documents Owned |
|---|---|
| **Data & ML Engineer** | `DATA_SOURCES.md`, `ARCHITECTURE_AND_DATA_SPEC.md`, `ML_SPEC.md` |
| **Backend & AWS Engineer** | `AWS_INFRA_AND_SECURITY.md`, `API_AND_FRONTEND_SPEC.md` (Backend section), `WORKFLOW.md` |
| **Frontend & BI Engineer** | `API_AND_FRONTEND_SPEC.md` (Frontend section), QuickSight section of `AWS_INFRA_AND_SECURITY.md` |
| **Team Lead / Storytelling** | `EXECUTION_PLAN.md`, `TESTING_AND_QA_CHECKLIST.md`, `idea-brief.md`, `build-summary.md` |
| **AI Coding Agents (All Roles)** | `ai_logs/README.md`, `ai_logs/SESSION_INDEX.md`, session log files in `ai_logs/` |

---

## Golden Rules Across All Documents

1. **Single Source of Truth:** When `EXECUTION_PLAN.md` task statuses or locked Day 1 decisions change, update both `EXECUTION_PLAN.md` and the current `ai_logs/` session log immediately.
2. **Zero Fabricated Data:** Every groundwater reading, rainfall record, and metric in docs/UI must originate from verifiable public datasets logged in `DATA_SOURCES.md`.
3. **Cost First:** Never spin up always-on SageMaker endpoints, NAT Gateways, or RDS instances. Verify AWS Budgets and teardown checks at the end of every AWS session.
4. **Core Path Protection:** Protect `Real Data -> Forecast -> Live API -> Live CloudFront Map` before adding optional polish (QuickSight, extra languages, visual extras).
