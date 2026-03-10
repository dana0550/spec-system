from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from specctl.agentic_epic import collect_repo_findings, synthesize_feature_artifacts, validate_feature_quality
from specctl.commands import render
from specctl.epic_index import read_epic_rows
from specctl.feature_index import read_feature_rows, write_feature_rows
from specctl.io_utils import now_date, set_frontmatter_value
from specctl.oneshot_utils import collect_traceability_stats, dump_json_document, load_json_document


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"
    features_path = docs / "FEATURES.md"
    epics_path = docs / "EPICS.md"

    feature_rows = read_feature_rows(features_path)
    feature_by_id = {row.feature_id: row for row in feature_rows}
    epics = read_epic_rows(epics_path)
    if args.epic_id:
        epics = [epic for epic in epics if epic.epic_id == args.epic_id]
        if not epics:
            print(f"[ERROR] Epic ID not found: {args.epic_id}")
            return 1

    dry_run = not bool(args.apply)

    findings = collect_repo_findings(root)
    upgrades: list[tuple[str, str, list[str]]] = []
    updated_feature_ids: set[str] = set()

    for epic in epics:
        epic_dir = docs / epic.epic_path
        oneshot_path = epic_dir / "oneshot.yaml"
        payload, err = load_json_document(oneshot_path)
        if err or payload is None:
            print(f"[WARN] Skipping {epic.epic_id}: {err}")
            continue

        scope = payload.get("scope_feature_ids", [])
        if not isinstance(scope, list):
            scope = []

        for feature_id in scope:
            row = feature_by_id.get(feature_id)
            if row is None:
                continue
            feature_dir = (docs / row.spec_path).parent
            issues = validate_feature_quality(feature_dir)
            if not issues:
                continue
            upgrades.append((epic.epic_id, feature_id, issues))
            if dry_run:
                continue

            if row.status in {"requirements_draft", "requirements_approved", "design_draft", "design_approved"}:
                row.status = "tasks_draft"
            artifacts = synthesize_feature_artifacts(
                row=row,
                owner=row.owner,
                root_feature_name=epic.name,
                findings=findings,
                answers={
                    "Q-AGENTIC-001": f"Backfilled KPI baseline for {epic.name}",
                    "Q-AGENTIC-002": "Backfilled constraints from existing brief and steering docs",
                },
            )
            for filename, text in artifacts.items():
                path = feature_dir / filename
                path.write_text(text, encoding="utf-8")
            updated_feature_ids.add(feature_id)

        if dry_run:
            continue

        payload.setdefault("synthesis_quality_profile", {})
        profile = payload["synthesis_quality_profile"]
        if isinstance(profile, dict):
            profile.setdefault(
                "minimums",
                {
                    "requirements": 3,
                    "scenarios": 2,
                    "design_decisions": 2,
                    "tasks": 3,
                },
            )
            profile.setdefault("research_log", "research.md")
            profile.setdefault("requires_no_tbd_evidence", True)

        payload.setdefault("approval_gates", {})
        if isinstance(payload["approval_gates"], dict):
            payload["approval_gates"].setdefault("mode", "migration")
            payload["approval_gates"].setdefault("migration_date", now_date())

        dump_json_document(oneshot_path, payload)

        research_path = epic_dir / "research.md"
        if not research_path.exists():
            research_path.write_text(
                "\n".join(
                    [
                        "# Research Log",
                        "",
                        "This file was backfilled during epic migrate-agentic.",
                        "",
                        "| Finding ID | Source | Type | Summary |",
                        "|---|---|---|---|",
                        "| FIND-MIGRATE-001 | migrate-agentic | migration | Existing deterministic artifacts were upgraded to agentic quality baseline. |",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

        for aux in ["questions.yaml", "answers.yaml", "agentic_state.json"]:
            path = epic_dir / aux
            if path.exists():
                continue
            if aux.endswith(".json"):
                path.write_text(
                    "{\n"
                    f'  "epic_id": "{epic.epic_id}",\n'
                    '  "status": "migration_backfilled"\n'
                    "}\n",
                    encoding="utf-8",
                )
            else:
                path.write_text("{}\n", encoding="utf-8")

    if upgrades:
        print("Agentic migration findings:")
        for epic_id, feature_id, issues in upgrades:
            issue_text = "; ".join(issues)
            print(f"- {epic_id} / {feature_id}: {issue_text}")
    else:
        print("No migration upgrades required.")

    if dry_run:
        print("Dry-run mode enabled (default). Re-run with --apply to write changes.")
        return 1 if upgrades else 0

    if updated_feature_ids:
        write_feature_rows(features_path, feature_rows, version="2.3.0")
        for feature_id in updated_feature_ids:
            row = feature_by_id.get(feature_id)
            if not row:
                continue
            feature_dir = (docs / row.spec_path).parent
            for filename in ["requirements.md", "design.md", "tasks.md", "verification.md"]:
                path = feature_dir / filename
                if path.exists():
                    set_frontmatter_value(path, "status", row.status)

    render_stats = collect_traceability_stats(docs, feature_rows)
    render_rc = render.run(Namespace(root=str(root), check=False, stats=render_stats))
    if render_rc != 0:
        print("[ERROR] Failed to render docs after migration apply")
        return 1

    print("Agentic migration apply completed.")
    return 0
