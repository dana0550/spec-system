---
name: docs-spec-system
description: Maintain a Markdown-only product spec system with FEATURES.md as the SSOT and deterministic propagation to feature specs and PRODUCT_MAP.md. Use when Codex must bootstrap docs, add or re-parent features, rename or deprecate features, update requirements and acceptance criteria with development status traceability, rebuild product map and backlinks, create or update ADRs, and prepare docs PR content using a template. Do not use this skill for legacy migration or code-audit workflows.
---

# Docs Spec System

Execute documentation changes through an SSOT-first workflow and keep all derived docs synchronized.

## Runbook

1. Read `references/spec-system-rules.md` before editing any docs files.
2. Choose the task playbook in `references/workflows.md`.
3. Update `FEATURES.md` first whenever feature identity, status, or hierarchy changes.
4. Propagate updates to feature specs, `MASTER_SPEC.md`, and `PRODUCT_MAP.md`.
5. Rebuild AUTOGEN sections and run the integrity checklist from `references/spec-system-rules.md`.
6. Prepare release and PR artifacts using `references/release-and-pr.md` and `assets/docs-system-pr-template.md`.
7. Return a concise diff summary including impacted IDs, files touched, and validation outcomes.

## Required Output For Every Task

- List impacted feature IDs and operation type (`new`, `updated`, `renamed`, `deprecated`, `re-parented`).
- State which integrity checks passed or failed.
- Note follow-up work if any item is intentionally deferred.
- Keep ID references stable (`[F-###]`) and avoid name-only references for traceability.

## Out-of-Scope Handling

If the user requests legacy migration, code-audit inference, or script-driven scaffolding, state that this skill v1 intentionally excludes migration/audit workflows and continue with docs-only SSOT operations.

## Skill Resources

- `references/spec-system-rules.md`: Canonical schemas, markers, propagation matrix, and integrity rules.
- `references/workflows.md`: Task-specific procedures and acceptance conditions.
- `references/release-and-pr.md`: Post-change validation and PR assembly flow.
- `assets/docs-system-pr-template.md`: PR body template to populate with concrete data.
