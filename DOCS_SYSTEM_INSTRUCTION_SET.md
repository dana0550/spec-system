---
doc_type: notice
name: docs_system_instruction_set_deprecated
version: 2.0.0
last_updated: 2026-02-06
---
# Docs System Instruction Set (Deprecated In Repo Form)

This repository no longer distributes the docs system as standalone script-driven instructions.

Use the `docs-spec-system` Codex Skill instead:
- Skill entrypoint: `skills/docs-spec-system/SKILL.md`
- Canonical rules: `skills/docs-spec-system/references/spec-system-rules.md`
- Task playbooks: `skills/docs-spec-system/references/workflows.md`
- PR and release flow: `skills/docs-spec-system/references/release-and-pr.md`

## Supported Interface

Invoke the skill directly in Codex prompts:
- `Use $docs-spec-system to bootstrap docs for this repository.`
- `Use $docs-spec-system to apply feature lifecycle updates and regenerate maps/backlinks.`

## Unsupported In v1

- Legacy migration and code-audit workflows.
- Script-driven sync/migrate commands.

For installation and usage details, see `README.md`.
