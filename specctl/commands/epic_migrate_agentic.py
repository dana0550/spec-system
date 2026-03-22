from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from specctl.agentic_epic import (
    AgenticQuestion,
    collect_repo_findings,
    is_interactive_mode,
    load_answers_file,
    resolve_questions,
    synthesize_feature_artifacts,
    validate_feature_quality,
    write_question_pack,
)
from specctl.commands import render
from specctl.constants import NEEDS_INPUT_EXIT_CODE
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
    runner = args.runner or "codex"
    interactive = is_interactive_mode(bool(getattr(args, "interactive", False)), bool(getattr(args, "no_interactive", False)))
    answers_file = Path(args.answers_file).resolve() if getattr(args, "answers_file", None) else None
    provided_answers = load_answers_file(answers_file)
    question_pack_path = (
        Path(args.question_pack_out).resolve()
        if getattr(args, "question_pack_out", None)
        else (root / "agentic-migrate-question-pack.yaml")
    )
    question_mode_enabled = bool(
        getattr(args, "answers_file", None)
        or getattr(args, "interactive", False)
        or getattr(args, "no_interactive", False)
        or getattr(args, "question_pack_out", None)
    )

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

        default_answers = {
            "Q-AGENTIC-001": f"Backfilled KPI baseline for {epic.name}",
            "Q-AGENTIC-002": "Backfilled constraints from existing brief and steering docs",
        }
        effective_answers = dict(default_answers)
        effective_answers.update(provided_answers)
        if question_mode_enabled:
            questions = [
                AgenticQuestion(
                    question_id="Q-AGENTIC-001",
                    text=f"What KPI should be prioritized for migrated epic '{epic.name}'?",
                    required=True,
                    source="migration",
                ),
                AgenticQuestion(
                    question_id="Q-AGENTIC-002",
                    text=f"Any additional migration constraints for epic '{epic.name}'?",
                    required=True,
                    source="migration",
                ),
            ]
            resolved_answers, pending = resolve_questions(
                questions=questions,
                seed_answers=dict(provided_answers),
                interactive=interactive,
            )
            if pending:
                write_question_pack(
                    question_pack_path,
                    epic_name=epic.name,
                    questions=pending,
                    answers=resolved_answers,
                )
                print(
                    f"[NEEDS_INPUT] Missing required migration answers for {epic.epic_id}; "
                    f"wrote question pack to {question_pack_path}"
                )
                return NEEDS_INPUT_EXIT_CODE
            effective_answers.update(resolved_answers)

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
                answers=effective_answers,
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
            profile.setdefault("migration_runner", runner)

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
                    f'  "runner": "{runner}",\n'
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
