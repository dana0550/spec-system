# Spec System Rules (v2.4)

Release: `docs-spec-system` v2.4.0.

## Canonical Model

- `docs/FEATURES.md` is the canonical feature registry.
- `docs/CONTRACT_CHANGES.md` is the canonical contract-change registry.
- `docs/EPICS.md` is the canonical epic registry.
- Each feature uses a folderized artifact set:
  - `requirements.md`
  - `design.md`
  - `tasks.md`
  - `verification.md`
- Each epic uses a folderized one-shot artifact set:
  - `brief.md`
  - `decomposition.yaml`
  - `oneshot.yaml`
  - `research.md` (agentic mode)
  - `questions.yaml` (agentic mode)
  - `answers.yaml` (agentic mode)
  - `agentic_state.json` (agentic mode)
  - `memory/`
  - `runs/`
- Each contract change uses a single markdown artifact under `docs/contracts/`:
  - `CC-###-<slug>.md`
- `docs/PRODUCT_MAP.md` and `docs/TRACEABILITY.md` are generated artifacts.
- `docs/.specctl/impact-baseline.json` stores deterministic impact fingerprints and review anchors.
- `docs/MASTER_SPEC.md` and `docs/STEERING.md` define product and architecture constraints.

## Canonical Layout

```text
docs/
  MASTER_SPEC.md
  FEATURES.md
  CONTRACT_CHANGES.md
  EPICS.md
  PRODUCT_MAP.md
  TRACEABILITY.md
  STEERING.md
  .specctl/
    impact-baseline.json
  DECISIONS/
    ADR_TEMPLATE.md
  epics/
    E-001-<slug>/
      brief.md
      decomposition.yaml
      oneshot.yaml
      research.md
      questions.yaml
      answers.yaml
      agentic_state.json
      memory/
      runs/
  features/
    F-001-<slug>/
      requirements.md
      design.md
      tasks.md
      verification.md
  contracts/
    CC-001-<slug>.md
```

## ID Grammar

- Feature ID: `F-###` or dotted descendants (`F-001.01`, `F-001.01.01`)
- Epic ID: `E-###`
- Contract Change ID: `CC-###`
- Requirement ID: `R-F###(.##)*-###`
- Scenario ID: `S-F###(.##)*-###`
- Design decision ID: `D-F###(.##)*-###`
- Task ID: `T-F###(.##)*-###`
- One-shot checkpoint ID: `C-E###-###`
- One-shot blocker ID: `B-E###-###`

IDs are immutable after assignment.

## Epic Lifecycle States

Allowed states:

- `planning`
- `implementing`
- `verifying`
- `done`
- `blocked`
- `deprecated`

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

## Contract Change Lifecycle States

Allowed states:

- `draft`
- `approved`
- `published`
- `closed`

Current-state validation gates:

- `draft`: schema, required sections, and downstream table headers are valid.
- `approved`: same as `draft`, plus at least one fully populated downstream target (`repo`, `owner`, `context`).
- `published`: same as `approved`, plus all targets include `pr_url` and `state` in `opened|merged`.
- `closed`: same as `published`, plus all targets have `state=merged`.

Transition history is not enforced; status is edited manually and validated in current state by `specctl check`.

## Contract Change Schema

Required frontmatter:

- `doc_type: contract_change`
- `contract_change_id: CC-###`
- `name`
- `status`
- `change_type`
- `owner`
- `last_updated`

Required section headers:

- `## Summary`
- `## Contract Surface`
- `## Change Details`
- `## Compatibility and Migration Guidance`
- `## Downstream Notification Context`

Required downstream table columns:

- `repo`
- `owner`
- `context`
- `pr_url`
- `state`

Allowed target states:

- `pending`
- `opened`
- `merged`
- `blocked`

Allowed change types:

- `service_added` (new service standup / launch notification)
- `service_changed` (service behavior or interface evolution)
- `api_contract_added`
- `api_contract_changed`
- `api_contract_deprecated`
- `api_contract_removed`
- `custom` (requires `change_type_custom`)

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
- Feature lifecycle `status` in `FEATURES.md` must be synchronized into each feature artifact frontmatter.

Global contract:

- `R -> D -> T -> S -> evidence`
- Impact drift must be reviewed:
  - `specctl impact scan` reports direct (`added|changed|removed`) and propagated (`upstream_changed`) suspects.
  - `specctl impact refresh` updates baseline fingerprints.
  - `specctl impact refresh --ack-upstream` records explicit acknowledgment for unchanged downstream text.

Epic contract:

- `brief -> decomposition -> oneshot contract -> run checkpoints -> blocker ledger -> finalize evidence`
- Agentic epic create (`--mode agentic`) defaults to:
  - epic status `planning`
  - feature status `tasks_draft`
  - strict non-interactive input enforcement (`NEEDS_INPUT_EXIT_CODE=2`) when required answers are missing
- Deterministic epic create (`--mode deterministic`) remains backward-compatible and sets epic status `implementing`.
- Epic one-shot finalize requires:
  - zero open blockers
  - zero unresolved `ONESHOT-BLOCKER:*` markers
  - zero open impact suspects in scoped features
  - successful finalize validation command group
  - full scoped `R -> D -> T -> S -> evidence` traceability

## Generated Artifacts

- `docs/PRODUCT_MAP.md` is rendered from `FEATURES.md` hierarchy.
- `docs/TRACEABILITY.md` is rendered from feature traceability metrics.
- Epic one-shot reports are emitted via `specctl oneshot report`.

Generated files must be deterministic for identical inputs.

## CLI Interface (First-Class)

Required command surface:

- `specctl init`
- `specctl feature create`
- `specctl feature check`
- `specctl contract create`
- `specctl impact scan`
- `specctl impact refresh`
- `specctl epic create`
- `specctl epic check`
- `specctl epic migrate-agentic`
- `specctl codex setup`
- `specctl codex check`
- `specctl oneshot run`
- `specctl oneshot resume`
- `specctl oneshot check`
- `specctl oneshot finalize`
- `specctl oneshot report`
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
3. `EPICS.md` epic IDs are unique and valid.
4. `CONTRACT_CHANGES.md` contract IDs are unique and valid.
5. All feature, contract-change, and epic statuses are valid lifecycle states.
6. Each feature and epic folder contains required artifacts.
7. Contract-change docs satisfy required schema/sections and status gates.
8. Requirements satisfy EARS + RFC modality.
9. Scenario IDs exist and verification evidence is present.
10. Full traceability chain is complete.
11. One-shot contracts have valid checkpoint DAGs mapped to `T-*`.
12. Run blockers ledger schema is valid.
13. Rendered artifacts are up-to-date.
14. Impact baseline exists and gating suspects are resolved or acknowledged.
