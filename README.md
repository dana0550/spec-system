# docs-spec-system

This repository distributes the `docs-spec-system` Codex Skill and Spec System v2 CLI (`specctl`).

## What Changed In v2

- Phase-gated feature artifacts (`requirements`, `design`, `tasks`, `verification`)
- Mandatory EARS + RFC requirement language
- Mandatory Gherkin acceptance scenarios
- Strict traceability chain: `R -> D -> T -> S -> evidence`
- First-class CLI for deterministic lint/render/check/approve/migrate/report
- Migration command from v1 docs layout

## Install Skill

```bash
install-skill-from-github.py --repo <owner>/<repo> --path skills/docs-spec-system
```

Restart Codex after installation.

## CLI Usage

```bash
specctl init
specctl feature create --name "User Authentication" --owner team@example.com
specctl lint
specctl render
specctl check
specctl approve --feature-id F-001 --phase requirements
specctl migrate-v1-to-v2
specctl report
```

## Migration

For repositories using v1 docs shape:

```bash
specctl migrate-v1-to-v2
specctl check
```

Migration writes backups to `.specctl-backups/migrate-<timestamp>/`.

## Validation

```bash
python -m pytest
```

## Releases

Official releases are Git tags and GitHub Releases.

```bash
git fetch origin
git switch main
git pull --ff-only
git tag -a v2.0.0 -m "docs-spec-system v2.0.0"
git push origin v2.0.0
```

Release policy:

- Tag only from `main`.
- Tag must match `pyproject.toml` project version.
- Tag triggers `.github/workflows/release.yml`, which runs validation gates and publishes the GitHub Release.
- `.github/workflows/auto-tag-from-main.yml` automatically creates the version tag after merges to `main` when the tag does not already exist.

## Pull Request Auto-Merge

This repository defaults pull requests to auto-merge behavior via `.github/workflows/auto-merge.yml`.

Merge happens only when:

- Every check/status on the PR head commit is green.
- A bugbot check has completed successfully.
- Cursor bugbot has no unresolved review threads.

Human review is not required by this workflow.

Per-PR opt-out is available using either:

- PR template toggle: `- [x] Disable default auto-merge for this PR`
- Label override: `automerge:off`

## Repository Layout

```text
skills/docs-spec-system/
  SKILL.md
  references/
  assets/
specctl/
tests/
```
