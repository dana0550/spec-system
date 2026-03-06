# Workflows (v2.1)

All operations are phase-gated and validated with `specctl`.

## 1) Bootstrap v2

1. Run `specctl init`.
2. Add first feature with `specctl feature create`.
3. Run `specctl render`.
4. Run `specctl check`.

Acceptance:

- Required files exist.
- No blocking errors from `specctl check`.

## 2) Add Feature

1. Run `specctl feature create --name "<Feature>" --owner <owner>`.
2. Fill `requirements.md` with EARS+RFC statements and Gherkin scenarios.
3. Add design mappings in `design.md`.
4. Add implementation tasks in `tasks.md`.
5. Add scenario evidence placeholders in `verification.md`.
6. Run `specctl check`.

Acceptance:

- All IDs present and linked.
- Traceability chain complete.

## 3) Add Epic (Automatic Feature Tree + One-Shot Contract)

1. Prepare brief with required sections:
   - `Vision`
   - `Outcomes`
   - `User Journeys`
   - `Constraints`
   - `Non-Goals`
2. Run `specctl epic create --name "<Epic>" --owner <owner> --brief <brief.md>`.
3. Confirm epic scaffolding:
   - root feature created
   - child features generated from journeys/outcomes
   - component leaf features generated per child
   - one-shot artifacts created (`brief/decomposition/oneshot/memory/runs`)
4. Run `specctl epic check --epic-id <E-ID>`.
5. Run `specctl check`.

Acceptance:

- Epic tree is deterministic and linked in `FEATURES.md`.
- Epic one-shot contract is valid and checkpoint graph maps to `T-*`.
- No blocking errors from `specctl check`.

## 4) Epic One-Shot Execution

1. Start run: `specctl oneshot run --epic-id <E-ID> [--runner codex|claude]`.
2. Validate contract/run artifacts: `specctl oneshot check --epic-id <E-ID> [--run-id <RUN-ID>]`.
3. If needed, continue run: `specctl oneshot resume --epic-id <E-ID> --run-id <RUN-ID>`.
4. Close blockers and remove placeholders.
5. Finalize: `specctl oneshot finalize --epic-id <E-ID> --run-id <RUN-ID>`.
6. Report: `specctl oneshot report --epic-id <E-ID>`.

Acceptance:

- Run completes with zero open blockers.
- No unresolved `ONESHOT-BLOCKER:*` markers remain.
- Scoped features and epic are marked `done`.

## 5) Phase Approvals

1. Requirements approval:
   - Ensure requirements quality and traceability.
   - Run `specctl approve --feature-id <F-ID> --phase requirements`.
2. Design approval:
   - Ensure design maps all requirements.
   - Run `specctl approve --feature-id <F-ID> --phase design`.
3. Tasks approval:
   - Ensure tasks map to requirement/design IDs.
   - Run `specctl approve --feature-id <F-ID> --phase tasks`.

Acceptance:

- Transition command succeeds with no lifecycle violation.

## 6) Migration (v1 -> v2)

1. Run `specctl migrate-v1-to-v2`.
2. Review generated `docs/MIGRATION_REPORT.md`.
3. Run `specctl check`.
4. Resolve blocking migration errors.

Acceptance:

- Feature docs are folderized.
- `FEATURES.md` paths point to v2 requirements docs.
- No blocking errors remain.

## 7) Bugfix Spec Workflow

1. Create or update feature artifacts for the affected capability.
2. Add regression scenario (`S-*`) describing failing behavior.
3. Add design update and tasks mapping for the fix.
4. Add verification evidence for the regression scenario.
5. Run `specctl check` and attach evidence.

Acceptance:

- Regression scenario has evidence.
- Traceability chain remains complete.

## 8) Deprecation Workflow

1. Set feature status to `deprecated` in `FEATURES.md`.
2. Preserve feature artifact folder for historical traceability.
3. Re-render generated docs.
4. Run `specctl check`.

Acceptance:

- Deprecated features remain documented.
- No broken references.
