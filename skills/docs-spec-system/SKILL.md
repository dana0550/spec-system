---
name: docs-spec-system
description: Operate the Spec System v2 contract-first workflow with phase gates, EARS+RFC requirements, Gherkin scenarios, strict traceability, and first-class specctl enforcement.
---

# Docs Spec System v2

Run all docs-spec operations through the phase-gated v2.1 system.

## Runbook

1. Read `references/spec-system-rules.md` for mandatory schemas and gate invariants.
2. Select the workflow in `references/workflows.md` that matches the requested change.
3. Use `specctl` as the primary interface (`feature`, `epic`, `oneshot`, `lint`, `render`, `check`, `approve`).
4. Keep requirements, design, tasks, and verification artifacts synchronized per feature.
5. Enforce `R -> D -> T -> S -> evidence` traceability before completion.
6. For epic work, enforce one-shot contract execution (`run -> check -> finalize`) with blockers/memory artifacts.
7. Use `references/release-and-pr.md` and `assets/docs-system-pr-template.md` to assemble release/PR outputs.

## Required Output For Every Task

- List impacted IDs by type (`E`, `F`, `R`, `D`, `T`, `S`) and operation type.
- Report phase transitions performed (if any).
- Report `specctl check` result and blocking errors/warnings.
- For one-shot runs, report run ID, checkpoint results, blocker count, and finalize status.

## Out-of-Scope Handling

- Do not infer implementation status from source code without explicit evidence.
- Do not run legacy v1 script workflows.
- Do not bypass phase gates unless the user explicitly requests a policy exception.
- Do not finalize one-shot runs with unresolved blocker ledger entries or placeholder markers.

## Skill Resources

- `references/spec-system-rules.md`: v2 schema, ID grammar, and quality gate rules.
- `references/workflows.md`: phase-driven execution playbooks.
- `references/release-and-pr.md`: PR assembly and release validation.
- `assets/docs-system-pr-template.md`: v2 PR template.
- `assets/templates/*.md`: canonical feature and governance templates.
