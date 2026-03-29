---
doc_type: feature_design
feature_id: F-001
status: tasks_approved
last_updated: 2026-03-29
---
# Repository Self Documentation Design

- D-F001-001: Implement R-F001-001 by codifying a bootstrap sequence in repository docs and preserving `specctl init -> feature create -> render -> check` as the canonical onboarding flow.
- D-F001-002: Implement R-F001-002 by treating README and `docs/MASTER_SPEC.md` + `docs/STEERING.md` as synchronized operator-facing guidance artifacts.
- D-F001-003: Implement R-F001-003 by maintaining requirement/design/task/scenario IDs directly in feature folder artifacts and validating via `specctl feature check` and `specctl check`.
- D-F001-004: Implement R-F001-004 by documenting lifecycle and blocker policies in `docs/STEERING.md` and linking enforcement to `specctl approve` and one-shot finalize gates.
