# Workflows (v2)

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

## 3) Phase Approvals

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

## 4) Migration (v1 -> v2)

1. Run `specctl migrate-v1-to-v2`.
2. Review generated `docs/MIGRATION_REPORT.md`.
3. Run `specctl check`.
4. Resolve blocking migration errors.

Acceptance:

- Feature docs are folderized.
- `FEATURES.md` paths point to v2 requirements docs.
- No blocking errors remain.

## 5) Bugfix Spec Workflow

1. Create or update feature artifacts for the affected capability.
2. Add regression scenario (`S-*`) describing failing behavior.
3. Add design update and tasks mapping for the fix.
4. Add verification evidence for the regression scenario.
5. Run `specctl check` and attach evidence.

Acceptance:

- Regression scenario has evidence.
- Traceability chain remains complete.

## 6) Deprecation Workflow

1. Set feature status to `deprecated` in `FEATURES.md`.
2. Preserve feature artifact folder for historical traceability.
3. Re-render generated docs.
4. Run `specctl check`.

Acceptance:

- Deprecated features remain documented.
- No broken references.
