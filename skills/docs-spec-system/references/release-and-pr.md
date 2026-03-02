# Release And PR Workflow (v2)

## Required Validation Before PR

1. `specctl lint`
2. `specctl render --check`
3. `specctl check`
4. Unit and integration tests

Blocking condition:

- Any `ERROR` in lint/check output.

## PR Assembly

1. Use `assets/docs-system-pr-template.md`.
2. Include all impacted IDs (`F`, `R`, `D`, `T`, `S`).
3. Include phase approvals performed.
4. Include migration notes (if `migrate-v1-to-v2` was used).
5. Include traceability and verification evidence links.
6. Include exact command outputs used for validation.

## Release Gates

- No placeholders in PR template.
- `specctl check` passes.
- Migration path documented for users.
- README and agent prompt are aligned with v2 command interface.

## Official Release Process

1. Merge approved PR into `main`.
2. Update `pyproject.toml` version if needed.
3. Create annotated SemVer tag from `main` (`vMAJOR.MINOR.PATCH`).
4. Push tag to origin.
5. GitHub Action `release.yml` validates:
   - tag commit is on `main`
   - tag matches `pyproject.toml` version
   - `specctl lint`, `specctl render --check`, `specctl check`, and tests pass
6. On pass, workflow publishes GitHub Release for the tag.

Automation note:

- `auto-tag-from-main.yml` creates and pushes `v<pyproject.version>` automatically on `main` pushes if missing, which then triggers `release.yml`.

## Suggested PR Title

`docs: spec system v2 update [F-IDs]`
