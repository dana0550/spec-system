from __future__ import annotations

from pathlib import Path

from specctl.constants import APPROVAL_TRANSITIONS
from specctl.feature_index import read_feature_rows, write_feature_rows
from specctl.io_utils import set_frontmatter_value


def run(args) -> int:
    root = Path(args.root).resolve()
    features_path = root / "docs" / "FEATURES.md"
    rows = read_feature_rows(features_path)

    if args.phase not in APPROVAL_TRANSITIONS:
        print(f"[ERROR] Unknown phase '{args.phase}'")
        return 1

    expected_from, target = APPROVAL_TRANSITIONS[args.phase]

    for row in rows:
        if row.feature_id != args.feature_id:
            continue
        if row.status != expected_from:
            print(
                f"[ERROR] Transition blocked for {row.feature_id}: expected '{expected_from}', found '{row.status}'"
            )
            return 1
        row.status = target
        write_feature_rows(features_path, rows)
        _sync_feature_status(root, row.spec_path, target)
        print(f"Approved {args.phase} for {row.feature_id} -> {target}")
        return 0

    print(f"[ERROR] Feature ID not found: {args.feature_id}")
    return 1


def _sync_feature_status(root: Path, spec_path: str, status: str) -> None:
    requirements_path = root / "docs" / spec_path
    feature_dir = requirements_path.parent
    for filename in ["requirements.md", "design.md", "tasks.md", "verification.md"]:
        path = feature_dir / filename
        if path.exists():
            set_frontmatter_value(path, "status", status)
