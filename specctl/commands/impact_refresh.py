from __future__ import annotations

from specctl.command_utils import project_root
from specctl.feature_index import read_feature_rows
from specctl.impact import refresh_impact_baseline


def run(args) -> int:
    root = project_root(args.root)
    feature_id = getattr(args, "feature_id", None)
    feature_ids = None
    if feature_id:
        rows = read_feature_rows(root / "docs" / "FEATURES.md")
        if feature_id not in {row.feature_id for row in rows}:
            print(f"[ERROR] Feature ID not found: {feature_id}")
            return 1
        feature_ids = {feature_id}

    rc, message, suspects, refreshed = refresh_impact_baseline(
        root,
        feature_ids=feature_ids,
        ack_upstream=bool(args.ack_upstream),
    )

    if rc == 0:
        print(message)
        print(f"- features_refreshed: {refreshed}")
        return 0

    if rc == 2:
        print(f"[ERROR] IMPACT_BASELINE_MISSING: {message}")
        return 2

    if suspects:
        print(f"[ERROR] IMPACT_SUSPECT_OPEN: {message}")
        print(f"- suspects_open: {len(suspects)}")
        print("- Run `specctl impact scan --root .` to inspect details.")
        if not args.ack_upstream:
            hint = "specctl impact refresh --root . --ack-upstream"
            if feature_id:
                hint += f" --feature-id {feature_id}"
            print(f"- If downstream text is intentionally unchanged, run `{hint}`.")
        return 1

    print(f"[ERROR] {message}")
    return 1
