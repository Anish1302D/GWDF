# WellCast AI Session Logs (`ai_logs/`)

This directory maintains a **persistent, chronological memory** of every development session (human or AI-assisted) performed on the WellCast project. It prevents context loss between sessions, tracks locked engineering decisions, records exact verification outputs, and ensures safe handoffs across the 7-day hackathon sprint.

---

## Mandatory Protocol for Every AI Session

### 1. Before Doing Any Work (Start-of-Session Read)
1. Open [`SESSION_INDEX.md`](./SESSION_INDEX.md) to see the full project timeline at a glance.
2. Read the **latest session log** (`YYYY-MM-DD_session-XX_*.md`) — especially its **Handoff & Next Session Instructions** and **Open Blockers** sections.
3. Read [`../Docs/EXECUTION_PLAN.md`](../Docs/EXECUTION_PLAN.md) §2 (Locked Decisions) and §7 (Master Progress Tracker) to confirm what is done vs pending.

### 2. While Working
- Follow the technical specifications in [`../Docs/`](../Docs/README.md) rather than inventing conflicting schemas or API contracts.
- Never fabricate dataset metrics, test outputs, or AWS verification results. Log only observed facts.
- If a locked decision (`D-01`–`D-08`) changes or a fallback is triggered, record the **exact reason and date** immediately.

### 3. Before Ending the Session (End-of-Session Write)
1. Create a new session log file in `ai_logs/` using [`TEMPLATE.md`](./TEMPLATE.md) with naming convention:
   ```text
   YYYY-MM-DD_session-XX_<short-kebab-topic>.md
   ```
   Example: `2026-11-24_session-03_phase0-aws-setup-and-data-audit.md`
2. Append a summary row to [`SESSION_INDEX.md`](./SESSION_INDEX.md).
3. Update completed checkboxes in [`../Docs/EXECUTION_PLAN.md`](../Docs/EXECUTION_PLAN.md) §7.
4. Record the exact **AWS Cost & Idle Resource State** whenever AWS resources were touched.

---

## Status Tag Conventions

- `[DONE]` — Completed and verified against its exit check.
- `[PARTIAL]` — Work started; remaining sub-tasks listed in Handoff.
- `[BLOCKED]` — Waiting on external dependency (e.g., AWS verification, portal download, credentials).
- `[DECISION]` — Architecture, dataset, or scope choice locked or revised.
- `[FALLBACK]` — Planned fallback path activated from `IMPLEMENTATION_PLAN.md`.
