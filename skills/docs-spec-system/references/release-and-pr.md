# Release And PR Workflow

Use this flow after any docs-system change set.

## Post-Change Validation

1. Run integrity checks from `references/spec-system-rules.md`.
2. Confirm impacted IDs are consistent across:
- `docs/FEATURES.md`
- `docs/features/*.md`
- `docs/PRODUCT_MAP.md`
3. Confirm all required AUTOGEN blocks exist and are refreshed.
4. Confirm changelog updates were appended for touched feature specs.
5. Confirm deprecated features are in deprecated map sections only.

## PR Assembly Procedure

1. Load `assets/docs-system-pr-template.md`.
2. Replace every guidance comment with concrete details from current diffs.
3. Fill summary with 2-3 bullets describing what changed and why.
4. Fill Feature Coverage with all touched IDs (new/updated/deprecated/re-parented/renamed).
5. Fill Decisions & ADRs with created/updated/superseded ADR IDs.
6. Tick only completed integrity checklist items.
7. Add verification notes (tests, lint, manual QA, integrity validation).
8. Add follow-ups/risks for rollout, budgets, or security items.

## PR Quality Gates

- No placeholder text remains in PR template fields.
- All touched features appear in Feature Coverage.
- ADR references resolve.
- Validation evidence is explicit and reproducible.

## Suggested Prompt Pattern

Use `$docs-spec-system` to prepare a docs PR for `[F-IDs]`, populate the PR template from `assets/docs-system-pr-template.md`, include ADR/test/integrity evidence, and output a ready-to-submit PR body with no placeholders.

## Suggested PR Title Format

`docs: <concise summary> [F-IDs]`
