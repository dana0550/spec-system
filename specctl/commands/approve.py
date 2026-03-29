from __future__ import annotations

from pathlib import Path

from specctl.command_utils import format_message
from specctl.constants import APPROVAL_TRANSITIONS
from specctl.feature_index import read_feature_rows, write_feature_rows
from specctl.impact import build_gate_messages
from specctl.io_utils import set_frontmatter_value


def run(args) -> int:
    root = Path(args.root).resolve()
    features_path = root / "docs" / "FEATURES.md"
    rows = read_feature_rows(features_path)

    if args.phase not in APPROVAL_TRANSITIONS:
        print(f"[ERROR] Unknown phase '{args.phase}'")
        return 1

    transition = APPROVAL_TRANSITIONS[args.phase]
    allowed_from = transition["from"]
    target = transition["to"]

    for row in rows:
        if row.feature_id != args.feature_id:
            continue
        missing_files = _missing_feature_files(root, row.spec_path)
        if missing_files:
            for path in missing_files:
                print(f"[ERROR] Missing required feature file for approval: {path}")
            return 1
        if row.status not in allowed_from:
            if len(allowed_from) == 1:
                expected = f"expected '{allowed_from[0]}'"
            else:
                expected = "expected one of " + ", ".join(f"'{status}'" for status in allowed_from)
            print(
                f"[ERROR] Transition blocked for {row.feature_id}: {expected}, found '{row.status}'"
            )
            return 1
        impact_messages = build_gate_messages(root, {row.feature_id}, command_name="approve")
        if impact_messages:
            for message in impact_messages:
                print(format_message(message))
            return 1
        row.status = target
        write_feature_rows(features_path, rows)
        _sync_feature_status(root, row.spec_path, target)
        print(f"Approved {args.phase} for {row.feature_id} -> {target}")
        return 0

    print(f"[ERROR] Feature ID not found: {args.feature_id}")
    return 1


def _missing_feature_files(root: Path, spec_path: str) -> list[Path]:
    requirements_path = root / "docs" / spec_path
    feature_dir = requirements_path.parent
    required = [feature_dir / filename for filename in ["requirements.md", "design.md", "tasks.md", "verification.md"]]
    return [path for path in required if not path.exists()]


def _sync_feature_status(root: Path, spec_path: str, status: str) -> None:
    requirements_path = root / "docs" / spec_path
    feature_dir = requirements_path.parent
    for filename in ["requirements.md", "design.md", "tasks.md", "verification.md"]:
        path = feature_dir / filename
        if path.exists():
            set_frontmatter_value(path, "status", status)
