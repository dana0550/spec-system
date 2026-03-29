---
doc_type: steering
version: 2.4.0
last_reviewed: 2026-03-29
---
# Steering

## Product Constraints
- The canonical model MUST be maintained in `docs/` using the v2 folderized structure.
- `specctl` MUST be the first-class interface for bootstrap, validation, rendering, approvals, migration, and reporting.
- Feature and epic IDs MUST remain immutable after assignment.
- One-shot finalize MUST require zero open blockers and zero unresolved placeholder markers.
- Generated docs (`PRODUCT_MAP.md`, `TRACEABILITY.md`) MUST be deterministic and reproducible.

## Design Principles
- Contract-first by default: requirements define behavior before implementation planning.
- Phase-gated quality: requirements, design, and task approvals are explicit lifecycle transitions.
- Evidence-driven verification: each scenario maps to concrete evidence artifacts.
- Agent portability: skill bundles and references remain compatible with Codex and Claude workflows.
