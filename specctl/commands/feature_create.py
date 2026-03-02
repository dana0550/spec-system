from __future__ import annotations

from pathlib import Path

from specctl.constants import FEATURE_STATUSES
from specctl.feature_index import FeatureRow, next_child_id, next_top_level_id, read_feature_rows, write_feature_rows
from specctl.io_utils import now_date, slugify, write_text
from specctl.validators.ids import FEATURE_ID_RE


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"
    features_index = docs / "FEATURES.md"
    rows = read_feature_rows(features_index)
    existing_ids = {row.feature_id for row in rows}

    if args.parent_id and args.parent_id not in existing_ids:
        print(f"[ERROR] Parent ID not found: {args.parent_id}")
        return 1

    feature_id = args.feature_id
    auto_generated = not feature_id
    if auto_generated:
        feature_id = next_child_id(rows, args.parent_id) if args.parent_id else next_top_level_id(rows)

    if not FEATURE_ID_RE.match(feature_id):
        if auto_generated:
            print("[ERROR] Cannot auto-generate feature ID: numbering space exhausted")
        else:
            print(f"[ERROR] Invalid feature ID format: {feature_id}")
        return 1
    if feature_id in existing_ids:
        print(f"[ERROR] Feature ID already exists: {feature_id}")
        return 1

    name = args.name.strip()
    status = args.status
    if status not in FEATURE_STATUSES:
        print(f"[ERROR] Invalid lifecycle status '{status}'")
        return 1
    slug = f"{feature_id}-{slugify(name)}"
    spec_path = f"features/{slug}/requirements.md"

    row = FeatureRow(
        feature_id=feature_id,
        name=name,
        status=status,
        parent_id=args.parent_id or "",
        spec_path=spec_path,
        owner=args.owner or "unassigned",
        aliases="[]",
    )
    rows.append(row)
    rows.sort(key=lambda r: r.feature_id)
    write_feature_rows(features_index, rows)

    feature_dir = docs / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)

    write_text(
        feature_dir / "requirements.md",
        "\n".join(
            [
                "---",
                "doc_type: feature_requirements",
                f"feature_id: {feature_id}",
                f"name: {name}",
                f"status: {status}",
                f"owner: {args.owner or 'unassigned'}",
                f"last_updated: {now_date()}",
                "---",
                f"# {name} Requirements",
                "",
                f"- R-{feature_id.replace('-', '')}-001: WHEN a user submits valid input, the system MUST process the request and return a success response.",
                f"- S-{feature_id.replace('-', '')}-001: Given valid input When the request is submitted Then the response status is 200.",
            ]
        )
        + "\n",
    )

    write_text(
        feature_dir / "design.md",
        "\n".join(
            [
                "---",
                "doc_type: feature_design",
                f"feature_id: {feature_id}",
                f"status: {status}",
                f"last_updated: {now_date()}",
                "---",
                f"# {name} Design",
                "",
                f"- D-{feature_id.replace('-', '')}-001: Implements R-{feature_id.replace('-', '')}-001 using the existing service boundary.",
            ]
        )
        + "\n",
    )

    write_text(
        feature_dir / "tasks.md",
        "\n".join(
            [
                "---",
                "doc_type: feature_tasks",
                f"feature_id: {feature_id}",
                f"status: {status}",
                f"last_updated: {now_date()}",
                "---",
                f"# {name} Tasks",
                "",
                f"- [ ] T-{feature_id.replace('-', '')}-001 Implement handler (R: R-{feature_id.replace('-', '')}-001, D: D-{feature_id.replace('-', '')}-001)",
            ]
        )
        + "\n",
    )

    write_text(
        feature_dir / "verification.md",
        "\n".join(
            [
                "---",
                "doc_type: feature_verification",
                f"feature_id: {feature_id}",
                f"status: {status}",
                f"last_updated: {now_date()}",
                "---",
                f"# {name} Verification",
                "",
                f"- S-{feature_id.replace('-', '')}-001: Given valid input When submitted Then response status is 200.",
                f"Evidence: S-{feature_id.replace('-', '')}-001 -> TBD",
            ]
        )
        + "\n",
    )

    print(f"Created feature {feature_id} at {feature_dir}")
    return 0
