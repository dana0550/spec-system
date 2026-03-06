from __future__ import annotations

from pathlib import Path

from specctl.constants import FEATURE_STATUSES
from specctl.feature_index import FeatureRow, next_child_id, next_top_level_id, read_feature_rows, write_feature_rows
from specctl.io_utils import now_date, slugify, write_text
from specctl.validators.ids import FEATURE_ID_RE


def create_feature_entry(
    rows: list[FeatureRow],
    *,
    name: str,
    status: str,
    owner: str,
    parent_id: str = "",
    feature_id: str | None = None,
) -> FeatureRow:
    existing_ids = {row.feature_id for row in rows}

    if parent_id and parent_id not in existing_ids:
        raise ValueError(f"Parent ID not found: {parent_id}")

    next_feature_id = feature_id
    auto_generated = not feature_id
    if auto_generated:
        next_feature_id = next_child_id(rows, parent_id) if parent_id else next_top_level_id(rows)

    if not FEATURE_ID_RE.match(next_feature_id):
        if auto_generated:
            raise ValueError("Cannot auto-generate feature ID: numbering space exhausted")
        raise ValueError(f"Invalid feature ID format: {next_feature_id}")
    if next_feature_id in existing_ids:
        raise ValueError(f"Feature ID already exists: {next_feature_id}")

    feature_name = name.strip()
    if status not in FEATURE_STATUSES:
        raise ValueError(f"Invalid lifecycle status '{status}'")
    slug = f"{next_feature_id}-{slugify(feature_name)}"
    spec_path = f"features/{slug}/requirements.md"

    return FeatureRow(
        feature_id=next_feature_id,
        name=feature_name,
        status=status,
        parent_id=parent_id,
        spec_path=spec_path,
        owner=owner or "unassigned",
        aliases="[]",
    )


def scaffold_feature_files(docs: Path, row: FeatureRow) -> Path:
    feature_dir = docs / Path(row.spec_path).parent
    feature_dir.mkdir(parents=True, exist_ok=True)
    scenario_text = "Given valid input When the request is submitted Then the response status is 200."
    feature_digits = row.feature_id.replace("-", "")
    feature_name = row.name
    status = row.status

    write_text(
        feature_dir / "requirements.md",
        "\n".join(
            [
                "---",
                "doc_type: feature_requirements",
                f"feature_id: {row.feature_id}",
                f"name: {feature_name}",
                f"status: {status}",
                f"owner: {row.owner}",
                f"last_updated: {now_date()}",
                "---",
                f"# {feature_name} Requirements",
                "",
                f"- R-{feature_digits}-001: WHEN a user submits valid input, the system MUST process the request and return a success response.",
                f"- S-{feature_digits}-001: {scenario_text}",
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
                f"feature_id: {row.feature_id}",
                f"status: {status}",
                f"last_updated: {now_date()}",
                "---",
                f"# {feature_name} Design",
                "",
                f"- D-{feature_digits}-001: Implements R-{feature_digits}-001 using the existing service boundary.",
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
                f"feature_id: {row.feature_id}",
                f"status: {status}",
                f"last_updated: {now_date()}",
                "---",
                f"# {feature_name} Tasks",
                "",
                f"- [ ] T-{feature_digits}-001 Implement handler (R: R-{feature_digits}-001, D: D-{feature_digits}-001)",
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
                f"feature_id: {row.feature_id}",
                f"status: {status}",
                f"last_updated: {now_date()}",
                "---",
                f"# {feature_name} Verification",
                "",
                f"- S-{feature_digits}-001: {scenario_text}",
                f"Evidence: S-{feature_digits}-001 -> TBD",
            ]
        )
        + "\n",
    )
    return feature_dir


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"
    features_index = docs / "FEATURES.md"
    rows = read_feature_rows(features_index)

    try:
        row = create_feature_entry(
            rows,
            name=args.name,
            status=args.status,
            owner=args.owner or "unassigned",
            parent_id=args.parent_id or "",
            feature_id=args.feature_id,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    rows.append(row)
    rows.sort(key=lambda r: r.feature_id)
    write_feature_rows(features_index, rows)

    feature_dir = scaffold_feature_files(docs, row)
    print(f"Created feature {row.feature_id} at {feature_dir}")
    return 0
