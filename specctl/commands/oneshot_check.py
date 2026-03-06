from __future__ import annotations

from specctl.command_utils import format_message, project_root
from specctl.commands.oneshot_common import load_epic_and_contract
from specctl.feature_index import read_feature_rows
from specctl.validators.oneshot import validate_oneshot_contract, validate_run_artifacts


def run(args) -> int:
    root = project_root(args.root)
    loaded, err = load_epic_and_contract(root, args.epic_id)
    if err:
        print(f"[ERROR] {err}")
        return 1
    epic = loaded["epic"]
    epic_dir: Path = loaded["epic_dir"]
    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    feature_by_id = {row.feature_id: row for row in rows}
    messages, _ = validate_oneshot_contract(root, epic, feature_by_id)
    messages.extend(validate_run_artifacts(epic_dir, run_id=args.run_id))
    for message in messages:
        print(format_message(message))
    return 1 if any(message.severity == "ERROR" for message in messages) else 0
