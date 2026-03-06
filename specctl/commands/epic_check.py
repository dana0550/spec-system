from __future__ import annotations

from pathlib import Path

from specctl.command_utils import format_message, project_root
from specctl.epic_index import read_epic_rows
from specctl.feature_index import read_feature_rows
from specctl.validators.oneshot import validate_oneshot_contract, validate_run_artifacts


def run(args) -> int:
    root = project_root(args.root)
    docs = root / "docs"
    epics = read_epic_rows(docs / "EPICS.md")
    epic = next((row for row in epics if row.epic_id == args.epic_id), None)
    if epic is None:
        print(f"[ERROR] Epic ID not found: {args.epic_id}")
        return 1
    feature_rows = read_feature_rows(docs / "FEATURES.md")
    feature_by_id = {row.feature_id: row for row in feature_rows}
    messages, _ = validate_oneshot_contract(root, epic, feature_by_id)
    messages.extend(validate_run_artifacts(docs / epic.epic_path))
    for message in messages:
        print(format_message(message))
    return 1 if any(message.severity == "ERROR" for message in messages) else 0
