# Spec System Rules (v2)

Release: `docs-spec-system` v2.0.0.

## Canonical Model

- `docs/FEATURES.md` is the canonical feature registry.
- Each feature uses a folderized artifact set:
  - `requirements.md`
  - `design.md`
  - `tasks.md`
  - `verification.md`
- `docs/PRODUCT_MAP.md` and `docs/TRACEABILITY.md` are generated artifacts.
- `docs/MASTER_SPEC.md` and `docs/STEERING.md` define product and architecture constraints.

## Canonical Layout

```text
docs/
  MASTER_SPEC.md
  FEATURES.md
  PRODUCT_MAP.md
  TRACEABILITY.md
  STEERING.md
  DECISIONS/
    ADR_TEMPLATE.md
  features/
    F-001-<slug>/
      requirements.md
      design.md
      tasks.md
      verification.md
```

## ID Grammar

- Feature ID: `F-###` or dotted descendants (`F-001.01`, `F-001.01.01`)
- Requirement ID: `R-F###(.##)*-###`
- Scenario ID: `S-F###(.##)*-###`
- Design decision ID: `D-F###(.##)*-###`
- Task ID: `T-F###(.##)*-###`

IDs are immutable after assignment.

## Feature Lifecycle States

Allowed states:

- `requirements_draft`
- `requirements_approved`
- `design_draft`
- `design_approved`
- `tasks_draft`
- `tasks_approved`
- `implementing`
- `verifying`
- `done`
- `deprecated`

Approval transitions:

- `requirements_draft -> requirements_approved`
- `design_draft -> design_approved`
- `tasks_draft -> tasks_approved`

## Requirements Contract

- Requirements MUST use EARS patterns and RFC 2119/8174 modal keywords.
- Modal keywords MUST be uppercase (`MUST`, `SHOULD`, `MAY`, etc.).
- Each requirement line format:
  - `- R-F...: <statement>`
- EARS trigger terms MUST appear (`WHEN`, `IF`, `WHILE`, `WHERE`, `WHENEVER`).

## Acceptance Scenario Contract

- Gherkin-style scenario statements are required.
- Scenario line format:
  - `- S-F...: Given ... When ... Then ...`

## Traceability Contract

Every feature must satisfy:

- `requirements.md` defines `R-*` and `S-*` IDs.
- `design.md` references every `R-*`.
- `tasks.md` references every `R-*` and corresponding `D-*`.
- `verification.md` includes scenario evidence markers:
  - `Evidence: S-F... -> <artifact>`

Global contract:

- `R -> D -> T -> S -> evidence`

## Generated Artifacts

- `docs/PRODUCT_MAP.md` is rendered from `FEATURES.md` hierarchy.
- `docs/TRACEABILITY.md` is rendered from feature traceability metrics.

Generated files must be deterministic for identical inputs.

## CLI Interface (First-Class)

Required command surface:

- `specctl init`
- `specctl feature create`
- `specctl lint`
- `specctl render`
- `specctl check`
- `specctl approve --phase ...`
- `specctl migrate-v1-to-v2`
- `specctl report`

## Severity Policy

- `ERROR`: blocking (`exit 1`)
- `WARN`: non-blocking unless strict mode
- `INFO`: advisory

## Integrity Checklist

1. Required root docs exist.
2. `FEATURES.md` feature IDs are unique and valid.
3. All feature statuses are valid lifecycle states.
4. Each feature folder contains required phase artifacts.
5. Requirements satisfy EARS + RFC modality.
6. Scenario IDs exist and verification evidence is present.
7. Full traceability chain is complete.
8. Rendered artifacts are up-to-date.
