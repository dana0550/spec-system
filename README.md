# docs-spec-system

This repository now distributes the `docs-spec-system` Codex Skill.

The skill provides a Markdown-only SSOT documentation workflow for:
- bootstrapping docs structure
- feature lifecycle operations (add, update, rename, re-parent, deprecate)
- requirements/acceptance criteria traceability maintenance
- ADR creation and updates
- docs PR preparation with a structured template

Legacy migration and code-audit workflows are intentionally out of scope in v1.

## Install

Install from this repository path using the skill installer tooling:

```bash
install-skill-from-github.py --repo <owner>/<repo> --path skills/docs-spec-system
```

After installation, restart Codex so the new skill is loaded.

## Use

Invoke with prompts such as:

- `Use $docs-spec-system to bootstrap docs for this project.`
- `Use $docs-spec-system to add feature "Clipboard Actions" as active.`
- `Use $docs-spec-system to rename F-002 and deprecate F-004.`
- `Use $docs-spec-system to prepare a docs PR for F-003 and F-007.`

## Repository Layout

```text
skills/
  docs-spec-system/
    SKILL.md
    agents/openai.yaml
    references/
      spec-system-rules.md
      workflows.md
      release-and-pr.md
    assets/
      docs-system-pr-template.md
```

## Deprecated Interfaces

These script interfaces are no longer supported:

- `python3 scripts/sync_instruction_set.py ...`
- `python3 scripts/migrate_existing_project.py ...`

All supported operations now flow through `$docs-spec-system`.

## Local Validation

Validate the skill package:

```bash
python3 /Users/dshakiba/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/docs-spec-system
```
