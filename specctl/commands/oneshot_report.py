from __future__ import annotations

import json

from specctl.command_utils import project_root
from specctl.epic_index import read_epic_rows
from specctl.oneshot_utils import collect_run_stats, scan_placeholder_markers


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
    run_stats = collect_run_stats(runs_dir)

    payload = {
        "epic_id": epic.epic_id,
        "epic_name": epic.name,
        "epic_status": epic.status,
        "runs_total": run_stats["runs_total"],
        "active_runs": run_stats["active_runs"],
        "checkpoints_passed": run_stats["checkpoints_passed"],
        "checkpoints_failed": run_stats["checkpoints_failed"],
        "blockers_opened": run_stats["blockers_opened"],
        "blockers_resolved": run_stats["blockers_resolved"],
        "placeholder_leakage_count": len(scan_placeholder_markers(root, exclude_prefixes=[docs / "epics"])),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("One-Shot Report")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0
