from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from specctl.commands.feature_create import create_feature_entry, scaffold_feature_files
from specctl.commands import render
from specctl.epic_index import next_epic_id, read_epic_rows, write_epic_rows
from specctl.feature_index import read_feature_rows, write_feature_rows
from specctl.io_utils import now_date, read_text, slugify, write_text
from specctl.models import EpicRow, FeatureRow, TraceabilityStats
from specctl.oneshot_utils import (
    REQUIRED_BRIEF_SECTIONS,
    checkpoint_id,
    default_components,
    dump_json_document,
    extract_bullets,
    needs_ui_components,
    parse_brief_sections,
)
from specctl.validators.ids import FEATURE_ID_RE
from specctl.validators.traceability import validate_feature_traceability


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"
    features_path = docs / "FEATURES.md"
    epics_path = docs / "EPICS.md"
    brief_path = Path(args.brief).resolve()

    if not brief_path.exists():
        print(f"[ERROR] Brief file not found: {brief_path}")
        return 1
    brief_text = read_text(brief_path)
    sections = parse_brief_sections(brief_text)
    missing_sections = [name for name in REQUIRED_BRIEF_SECTIONS if name not in sections]
    if missing_sections:
        print(f"[ERROR] brief.md missing required sections: {', '.join(missing_sections)}")
        return 1

    outcomes = extract_bullets(sections["Outcomes"])
    journeys = extract_bullets(sections["User Journeys"])
    child_names = journeys if journeys else outcomes
    source_mode = "user_journeys" if journeys else "outcomes"
    if not child_names:
        print("[ERROR] brief.md must include at least one bullet in User Journeys or Outcomes")
        return 1

    feature_rows = read_feature_rows(features_path)
    epic_rows = read_epic_rows(epics_path) if epics_path.exists() else []

    root_feature_id = args.feature_id
    if root_feature_id and not FEATURE_ID_RE.match(root_feature_id):
        print(f"[ERROR] Invalid feature ID format: {root_feature_id}")
        return 1
    if root_feature_id and any(row.feature_id == root_feature_id for row in feature_rows):
        print(f"[ERROR] Feature ID already exists: {root_feature_id}")
        return 1

    epic_id = next_epic_id(epic_rows)
    epic_slug = f"{epic_id}-{slugify(args.name)}"
    owner = args.owner or "unassigned"
    include_ui = needs_ui_components(brief_text)
    components = default_components(include_ui)

    working_rows: list[FeatureRow] = list(feature_rows)
    created_rows: list[FeatureRow] = []

    try:
        root_row = create_feature_entry(
            working_rows,
            name=args.name,
            status="requirements_draft",
            owner=owner,
            parent_id="",
            feature_id=root_feature_id,
        )
        working_rows.append(root_row)
        created_rows.append(root_row)
        scaffold_feature_files(docs, root_row)

        child_entries: list[dict[str, object]] = []
        for child_name in child_names:
            child_row = create_feature_entry(
                working_rows,
                name=child_name,
                status="requirements_draft",
                owner=owner,
                parent_id=root_row.feature_id,
            )
            working_rows.append(child_row)
            created_rows.append(child_row)
            scaffold_feature_files(docs, child_row)
            component_rows: list[FeatureRow] = []
            for component in components:
                component_row = create_feature_entry(
                    working_rows,
                    name=f"{child_name} - {component}",
                    status="requirements_draft",
                    owner=owner,
                    parent_id=child_row.feature_id,
                )
                working_rows.append(component_row)
                created_rows.append(component_row)
                component_rows.append(component_row)
                scaffold_feature_files(docs, component_row)
            child_entries.append(
                {
                    "feature_id": child_row.feature_id,
                    "name": child_row.name,
                    "components": [
                        {"feature_id": row.feature_id, "name": row.name}
                        for row in component_rows
                    ],
                }
            )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    working_rows.sort(key=lambda row: row.feature_id)
    write_feature_rows(features_path, working_rows, version="2.1.0")

    epic_row = EpicRow(
        epic_id=epic_id,
        name=args.name.strip(),
        status="implementing",
        root_feature_id=root_row.feature_id,
        epic_path=f"epics/{epic_slug}",
        owner=owner,
        aliases="[]",
    )
    epic_rows.append(epic_row)
    epic_rows.sort(key=lambda row: row.epic_id)
    write_epic_rows(epics_path, epic_rows, version="2.1.0")

    epic_dir = docs / epic_row.epic_path
    (epic_dir / "memory").mkdir(parents=True, exist_ok=True)
    (epic_dir / "runs").mkdir(parents=True, exist_ok=True)

    write_text(
        epic_dir / "brief.md",
        "\n".join(
            [
                "---",
                "doc_type: epic_brief",
                f"epic_id: {epic_id}",
                f"name: {args.name.strip()}",
                f"root_feature_id: {root_row.feature_id}",
                f"owner: {owner}",
                f"status: implementing",
                f"last_updated: {now_date()}",
                "---",
                "# Epic Brief",
                "",
                brief_text.strip(),
                "",
            ]
        ),
    )

    scope_feature_ids = [row.feature_id for row in created_rows]
    decomposition_payload = {
        "epic_id": epic_id,
        "name": args.name.strip(),
        "root_feature_id": root_row.feature_id,
        "source_mode": source_mode,
        "scope_feature_ids": scope_feature_ids,
        "children": child_entries,
        "generated_components": components,
    }
    dump_json_document(epic_dir / "decomposition.yaml", decomposition_payload)

    checkpoints = []
    previous_checkpoint = ""
    for idx, row in enumerate(created_rows, start=1):
        cid = checkpoint_id(epic_id, idx)
        checkpoints.append(
            {
                "checkpoint_id": cid,
                "name": row.name,
                "feature_id": row.feature_id,
                "task_ids": [f"T-{row.feature_id.replace('-', '')}-001"],
                "depends_on": [previous_checkpoint] if previous_checkpoint else [],
                "blocker_type": "implementation_gap",
            }
        )
        previous_checkpoint = cid

    oneshot_payload = {
        "epic_id": epic_id,
        "root_feature_id": root_row.feature_id,
        "scope_feature_ids": scope_feature_ids,
        "runner": "codex",
        "checkpoint_graph": checkpoints,
        "validation_commands": ["python -m specctl.cli lint --root ."],
        "repair_policy": {"max_retries_per_checkpoint": 2, "commands": []},
        "blocker_policy": {
            "hard_stop_types": [
                "data_loss_risk",
                "security_vulnerability",
                "destructive_migration_without_rollback",
                "compliance_privacy_breach",
                "broken_repository_integrity",
            ]
        },
        "finalize_gates": {
            "require_zero_open_blockers": True,
            "require_zero_placeholder_markers": True,
            "require_full_traceability": True,
            "required_validation_commands": ["python -m specctl.cli lint --root ."],
        },
    }
    dump_json_document(epic_dir / "oneshot.yaml", oneshot_payload)

    dump_json_document(
        epic_dir / "memory" / "state.json",
        {
            "epic_id": epic_id,
            "status": "planned",
            "last_checkpoint": "none",
            "checkpoint_status": {cp["checkpoint_id"]: "pending" for cp in checkpoints},
        },
    )
    write_text(epic_dir / "memory" / "resume_pack.md", "# Resume Pack\n\n- Epic initialized.\n")
    write_text(epic_dir / "memory" / "decisions.md", "# Decisions\n\n- Epic scaffold generated.\n")
    write_text(epic_dir / "memory" / "open_threads.md", "# Open Threads\n\n- None\n")

    render_stats = _collect_traceability_stats(docs, working_rows)
    render_rc = render.run(Namespace(root=str(root), check=False, stats=render_stats))
    if render_rc != 0:
        print("[ERROR] Failed to render project docs after epic creation.")
        return 1

    print(f"Created epic {epic_id} at {epic_dir}")
    print(f"Created {len(created_rows)} features in scope rooted at {root_row.feature_id}")
    return 0


def _collect_traceability_stats(docs: Path, feature_rows: list[FeatureRow]) -> TraceabilityStats:
    stats = TraceabilityStats()
    for row in feature_rows:
        feature_dir = (docs / row.spec_path).parent
        if not feature_dir.exists():
            continue
        _, trace_stats = validate_feature_traceability(feature_dir)
        stats.requirements_total += trace_stats.requirements_total
        stats.requirements_with_design += trace_stats.requirements_with_design
        stats.requirements_with_tasks += trace_stats.requirements_with_tasks
        stats.scenarios_total += trace_stats.scenarios_total
        stats.scenarios_with_evidence += trace_stats.scenarios_with_evidence
    return stats
