# Workflows (v2.4)

All operations are phase-gated and validated with `specctl`.

## 1) Bootstrap v2

1. Run `specctl init`.
2. Add first feature with `specctl feature create`.
3. Run `specctl render`.
4. Run `specctl impact refresh`.
5. Run `specctl check`.

Acceptance:

- Required files exist.
- No blocking errors from `specctl check`.

## 2) Add Feature

1. Run `specctl feature create --name "<Feature>" --owner <owner>`.
2. Fill `requirements.md` with EARS+RFC statements and Gherkin scenarios.
3. Add design mappings in `design.md`.
4. Add implementation tasks in `tasks.md`.
5. Add verification evidence plan in `verification.md`.
6. Run `specctl impact scan`.
7. Run `specctl check`.

Acceptance:

- All IDs present and linked.
- Traceability chain complete.
- Impact suspects are resolved or explicitly acknowledged.

## 2b) Add Contract Change

1. Run `specctl contract create --name "<Service Standup>" --owner <owner> --change-type service_added`.
   Use `service_changed` when evolving behavior or interfaces for an existing service.
2. Fill required sections in `docs/contracts/CC-###-<slug>.md`:
   - `Summary`
   - `Contract Surface`
   - `Change Details`
   - `Compatibility and Migration Guidance`
   - `Downstream Notification Context`
3. Add downstream target rows in the standard table with required fields (`repo`, `owner`, `context`, `pr_url`, `state`).
4. Keep `status` synchronized between `docs/CONTRACT_CHANGES.md` and contract-change frontmatter.
5. Run `specctl check`.

Acceptance:

- Contract change schema validates.
- Status gate requirements are met for the selected lifecycle state.
- No blocking errors from `specctl check`.

## 3) Add Epic (Agentic Default)

1. Prepare brief with required sections:
   - `Vision`
   - `Outcomes`
   - `User Journeys`
   - `Constraints`
   - `Non-Goals`
2. Run `specctl epic create --name "<Epic>" --owner <owner> --brief <brief.md>`.
3. For non-interactive agentic runs, provide `--answers-file` or capture unresolved prompts via `--question-pack-out`.
4. Confirm epic artifacts:
   - `brief.md`
   - `decomposition.yaml`
   - `oneshot.yaml`
   - `research.md`
   - `questions.yaml`
   - `answers.yaml`
   - `agentic_state.json`
5. Run `specctl epic check --epic-id <E-ID>`.
6. Run `specctl impact refresh`.
7. Run `specctl check`.

Acceptance:

- Agentic epic create ends in `planning`.
- Scoped features are generated in `tasks_draft`.
- Epic one-shot contract is valid and checkpoint graph maps to `T-*`.
- No blocking errors from `specctl check`.

## 3b) Deterministic Epic Fallback

1. Run `specctl epic create --mode deterministic --name "<Epic>" --owner <owner> --brief <brief.md>`.
2. Validate with `specctl epic check --epic-id <E-ID>` and `specctl check`.

Acceptance:

- Existing deterministic scaffold behavior is preserved.
- Deterministic epic create ends in `implementing`.

## 3c) Migrate Existing Epics To Agentic Quality

1. Dry run: `specctl epic migrate-agentic --check [--epic-id <E-ID>]`.
2. If strict input policy is required, use:
   - `--runner-policy strict`
   - `--answers-file <path>` or `--question-pack-out <path>` for non-interactive runs.
3. Apply: `specctl epic migrate-agentic --apply [--epic-id <E-ID>]`.
4. Re-run `specctl impact refresh` and `specctl check`.

Acceptance:

- Upgraded features satisfy quality baselines.
- Verification evidence does not contain `TBD`.
- Agentic artifacts exist for migrated epics.
- Re-running apply is idempotent.

## 4) Epic One-Shot Execution

1. Start run: `specctl oneshot run --epic-id <E-ID> [--runner codex|claude]`.
2. Validate contract/run artifacts: `specctl oneshot check --epic-id <E-ID> [--run-id <RUN-ID>]`.
3. If needed, continue run: `specctl oneshot resume --epic-id <E-ID> --run-id <RUN-ID>`.
4. Close blockers and remove placeholders.
5. Resolve impact suspects (`specctl impact scan`) and refresh baseline (`specctl impact refresh [--ack-upstream]`).
6. Finalize: `specctl oneshot finalize --epic-id <E-ID> --run-id <RUN-ID>`.
7. Report: `specctl oneshot report --epic-id <E-ID>`.

Acceptance:

- `oneshot run` transitions epic from `planning` to `implementing` when needed.
- Run completes with zero open blockers.
- No unresolved `ONESHOT-BLOCKER:*` markers remain.
- No open impact suspects remain in finalize scope.
- Scoped features and epic are marked `done`.

## 5) Phase Approvals

1. Requirements approval:
   - Ensure requirements quality and traceability.
   - Resolve impact suspects with `specctl impact refresh [--ack-upstream]`.
   - Run `specctl approve --feature-id <F-ID> --phase requirements`.
2. Design approval:
   - Ensure design maps all requirements.
   - Resolve impact suspects with `specctl impact refresh [--ack-upstream]`.
   - Run `specctl approve --feature-id <F-ID> --phase design`.
3. Tasks approval:
   - Ensure tasks map to requirement/design IDs.
   - Resolve impact suspects with `specctl impact refresh [--ack-upstream]`.
   - Run `specctl approve --feature-id <F-ID> --phase tasks`.

Acceptance:

- Transition command succeeds with no lifecycle violation.

## 6) Impact Baseline Maintenance

1. Run `specctl impact scan` to identify suspect links.
2. Update downstream artifacts where needed.
3. Run `specctl impact refresh`.
4. If downstream text is intentionally unchanged, run `specctl impact refresh --ack-upstream`.

Acceptance:

- `specctl impact scan` returns zero open suspects.

## 7) Migration (v1 -> v2)

1. Run `specctl migrate-v1-to-v2`.
2. Review `docs/MIGRATION_REPORT.md`.
3. Run `specctl check`.
4. Resolve blocking migration errors.

Acceptance:

- Feature docs are folderized.
- `FEATURES.md` paths point to v2 requirements docs.
- No blocking errors remain.

## 8) Bugfix Spec Workflow

1. Create or update feature artifacts for the affected capability.
2. Add regression scenario (`S-*`) describing failing behavior.
3. Add design update and tasks mapping for the fix.
4. Add verification evidence for the regression scenario.
5. Run `specctl check` and attach evidence.

Acceptance:

- Regression scenario has evidence.
- Traceability chain remains complete.

## 9) Deprecation Workflow

1. Set feature status to `deprecated` in `FEATURES.md`.
2. Preserve feature artifact folder for historical traceability.
3. Re-render generated docs.
4. Run `specctl check`.

Acceptance:

- Deprecated features remain documented.
- No broken references.
