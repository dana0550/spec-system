# AGENTS

Use `specctl` as the source of truth for spec operations in this repository.

## Workflow

- Run spec changes through phase-gated docs workflow (`requirements -> design -> tasks -> verification`).
- Keep strict `R -> D -> T -> S -> evidence` traceability.
- For epics, run one-shot lifecycle (`run -> check -> finalize`) with blocker closure.
- Prefer agentic epic planning for new epics and deterministic mode only when explicitly requested.

## Review guidelines

- Treat lifecycle regressions (planning/implementing transitions) as P1.
- Treat missing traceability links and placeholder evidence markers as P1.
- Treat weak agentic artifacts (`research.md`, `questions.yaml`, `answers.yaml`, `agentic_state.json`) as P1.
- Flag deterministic fallback in strict codex mode as P1.
