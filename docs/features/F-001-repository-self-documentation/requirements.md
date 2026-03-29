---
doc_type: feature_requirements
feature_id: F-001
name: Repository Self Documentation
status: tasks_approved
owner: dana0550
last_updated: 2026-03-29
---
# Repository Self Documentation Requirements

- R-F001-001: WHEN a contributor bootstraps the repository, the system MUST provide an explicit v2 startup path using `specctl init`, `specctl feature create`, `specctl render`, and `specctl check`.
- R-F001-002: WHEN the command surface changes, the system MUST update canonical docs so README and spec artifacts reference current `specctl` workflows and guidance entrypoints.
- R-F001-003: IF feature artifacts are updated, the system MUST preserve traceability from `R-*` to `D-*` to `T-*` to `S-*` with evidence markers.
- R-F001-004: WHERE repository documentation includes operational policies, it MUST describe phase gates, one-shot blocker controls, and non-goal boundaries to reduce misuse.
- S-F001-001: Given a clean clone When a maintainer follows bootstrap commands Then docs v2 artifacts are generated without manual file scaffolding.
- S-F001-002: Given a docs update touching command guidance When render and check are executed Then generated artifacts and references remain synchronized.
- S-F001-003: Given a feature requirements/design/tasks update When verification is reviewed Then each scenario has an evidence mapping entry.
- S-F001-004: Given operational policy documentation When an agent reads the steering artifacts Then lifecycle gates and blocker rules are explicitly discoverable.
