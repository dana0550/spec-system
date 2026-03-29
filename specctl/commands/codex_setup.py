from __future__ import annotations

import json
import stat
from pathlib import Path

from specctl.io_utils import write_text


AGENTS_TEMPLATE = """# AGENTS

Use `specctl` as the source of truth for spec operations in this repository.

## Workflow

- Run spec changes through phase-gated docs workflow (`requirements -> design -> tasks -> verification`).
- Run contract-change notifications through `CONTRACT_CHANGES.md` + `docs/contracts/CC-###-*.md`.
- Keep strict `R -> D -> T -> S -> evidence` traceability.
- For epics, run one-shot lifecycle (`run -> check -> finalize`) with blocker closure.
- Prefer agentic epic planning for new epics and deterministic mode only when explicitly requested.

## Review guidelines

- Treat lifecycle regressions (planning/implementing transitions) as P1.
- Treat missing traceability links and placeholder evidence markers as P1.
- Treat weak agentic artifacts (`research.md`, `questions.yaml`, `answers.yaml`, `agentic_state.json`) as P1.
- Flag deterministic fallback in strict codex mode as P1.
"""


CODEX_CONFIG_TEMPLATE = """# Project-scoped Codex configuration for Spec System.
model = "gpt-5.4"
profile = "spec-agentic"
project_doc_max_bytes = 65536

[profiles.spec-agentic]
model = "gpt-5.4"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
approval_policy = "on-request"
web_search = "cached"

[profiles.spec-ci]
model = "gpt-5.4-mini"
model_reasoning_effort = "medium"
sandbox_mode = "workspace-write"
approval_policy = "never"
web_search = "disabled"

[profiles.spec-review]
model = "gpt-5.4"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"
approval_policy = "never"
web_search = "cached"
"""


WORKTREE_SETUP_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f "pyproject.toml" ]]; then
  echo "pyproject.toml not found in $(pwd)"
  exit 1
fi

python -m specctl.cli check --root .
"""


PROJECT_ACTIONS_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
Spec System quick actions
1) specctl check --root .
2) specctl report --root . --json
3) specctl epic check --root . --epic-id E-001
4) specctl oneshot report --root . --epic-id E-001 --json
EOF
"""


AUTOMATION_SPEC_QUALITY = """# Spec Quality Check Automation Prompt

Run `specctl check --root .` and `specctl report --root . --json`.
Summarize errors and warnings by code and path.
If there are no errors, summarize drift risks and open quality gaps.
"""


AUTOMATION_MIGRATION_AUDIT = """# Agentic Migration Audit Automation Prompt

Run `specctl epic migrate-agentic --root . --check`.
Summarize which epics/features would be upgraded and why.
Highlight missing agentic artifacts and strict-input blockers.
"""


def run(args) -> int:
    root = Path(args.root).resolve()
    force = bool(getattr(args, "force", False))
    json_mode = bool(getattr(args, "json", False))

    file_templates: list[tuple[Path, str, bool]] = [
        (root / "AGENTS.md", AGENTS_TEMPLATE, False),
        (root / ".codex" / "config.toml", CODEX_CONFIG_TEMPLATE, False),
        (root / "scripts" / "codex" / "worktree-setup.sh", WORKTREE_SETUP_SCRIPT, True),
        (root / "scripts" / "codex" / "project-actions.sh", PROJECT_ACTIONS_SCRIPT, True),
        (root / "assets" / "codex" / "automations" / "spec-quality-check.md", AUTOMATION_SPEC_QUALITY, False),
        (root / "assets" / "codex" / "automations" / "migration-audit.md", AUTOMATION_MIGRATION_AUDIT, False),
    ]

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    for path, content, executable in file_templates:
        exists = path.exists()
        if exists and not force:
            skipped.append(str(path.relative_to(root)))
            continue
        write_text(path, content.rstrip() + "\n")
        if executable:
            current_mode = path.stat().st_mode
            path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        rel = str(path.relative_to(root))
        if exists:
            updated.append(rel)
        else:
            created.append(rel)

    payload = {
        "status": "ok",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "root": str(root),
    }
    if json_mode:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Codex compatibility setup complete.")
        print(f"Created: {len(created)} Updated: {len(updated)} Skipped: {len(skipped)}")
        for label, rows in [("created", created), ("updated", updated), ("skipped", skipped)]:
            if not rows:
                continue
            print(f"- {label}:")
            for row in rows:
                print(f"  - {row}")
    return 0
