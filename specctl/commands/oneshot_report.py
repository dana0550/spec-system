from __future__ import annotations

import json
from pathlib import Path

from specctl.command_utils import project_root
from specctl.epic_index import read_epic_rows
from specctl.oneshot_utils import parse_blockers, scan_placeholder_markers


def run(args) -> int:
    root = project_root(args.root)
    docs = root / "docs"
    epic_rows = read_epic_rows(docs / "EPICS.md")
    epic = next((row for row in epic_rows if row.epic_id == args.epic_id), None)
    if epic is None:
        print(f"[ERROR] Epic ID not found: {args.epic_id}")
        return 1

    epic_dir = docs / epic.epic_path
    runs_dir = epic_dir / "runs"
    active_runs = 0
    checkpoints_passed = 0
    checkpoints_failed = 0
    blockers_opened = 0
    blockers_resolved = 0
    run_count = 0

    if runs_dir.exists():
        for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
            run_count += 1
            state_path = run_dir / "state.json"
            if state_path.exists():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    state = {}
                if state.get("status") in {"running", "stabilizing"}:
                    active_runs += 1
                checkpoint_status = state.get("checkpoint_status", {})
                if isinstance(checkpoint_status, dict):
                    checkpoints_passed += sum(1 for value in checkpoint_status.values() if value == "passed")
                    checkpoints_failed += sum(
                        1 for value in checkpoint_status.values() if value in {"failed_terminal", "blocked_with_placeholder"}
                    )
            for blocker in parse_blockers(run_dir / "blockers.md"):
                if blocker["status"] == "open":
                    blockers_opened += 1
                if blocker["status"] == "resolved":
                    blockers_resolved += 1

    payload = {
        "epic_id": epic.epic_id,
        "epic_name": epic.name,
        "epic_status": epic.status,
        "runs_total": run_count,
        "active_runs": active_runs,
        "checkpoints_passed": checkpoints_passed,
        "checkpoints_failed": checkpoints_failed,
        "blockers_opened": blockers_opened,
        "blockers_resolved": blockers_resolved,
        "placeholder_leakage_count": len(scan_placeholder_markers(root, exclude_prefixes=[docs / "epics"])),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("One-Shot Report")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0
