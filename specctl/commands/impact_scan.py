from __future__ import annotations

import json

from specctl.command_utils import project_root
from specctl.feature_index import read_feature_rows
from specctl.impact import scan_impact, suspects_to_json


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

    result = scan_impact(root, feature_ids=feature_ids)
    payload = {
        "suspects_open": len(result.suspects),
        "features_scanned": result.features_scanned,
        "baseline_status": result.baseline_status,
        "suspects": suspects_to_json(result.suspects),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text_report(payload, feature_id=feature_id)

    if result.baseline_status != "ok":
        return 2
    return 1 if result.suspects else 0


def _print_text_report(payload: dict, *, feature_id: str | None) -> None:
    suspects = payload["suspects"]
    print("Impact Scan")
    print(f"- suspects_open: {payload['suspects_open']}")
    print(f"- features_scanned: {payload['features_scanned']}")
    print(f"- baseline_status: {payload['baseline_status']}")

    if payload["baseline_status"] != "ok":
        print("- next_step: run `specctl impact refresh --root .`")
        return

    if not suspects:
        print("- next_step: no action required")
        return

    print("")
    print("| Feature | Entity | Reason | Upstream | Path |")
    print("|---|---|---|---|---|")
    for suspect in suspects:
        entity = f"{suspect['entity_type']}:{suspect['entity_id']}"
        upstream = ", ".join(suspect["upstream_ids"]) if suspect["upstream_ids"] else "-"
        path = _format_path(suspect["path"], suspect["line"])
        print(f"| {suspect['feature_id']} | {entity} | {suspect['reason']} | {upstream} | {path} |")

    refresh_command = "specctl impact refresh --root ."
    if feature_id:
        refresh_command += f" --feature-id {feature_id}"
    print("")
    print(f"- next_step: run `{refresh_command}` after downstream updates")
    if any(suspect["reason"] == "upstream_changed" for suspect in suspects):
        print(f"- if intentional: run `{refresh_command} --ack-upstream`")


def _format_path(path: str, line: int | None) -> str:
    if line is None:
        return path
    return f"{path}:{line}"
