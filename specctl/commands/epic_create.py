from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from specctl.agentic_epic import (
    AgenticQuestion,
    ask_approval_gate,
    build_adaptive_nodes,
    collect_repo_findings,
    default_questions,
    invoke_runner,
    is_interactive_mode,
    load_answers_file,
    merge_questions,
    render_research_log,
    resolve_questions,
    resolve_runner_command,
    synthesize_feature_artifacts,
    write_agentic_artifacts,
    write_question_pack,
)
from specctl.commands import render
from specctl.commands.feature_create import create_feature_entry, scaffold_feature_files
from specctl.constants import AGENTIC_QUALITY_MINIMUMS, NEEDS_INPUT_EXIT_CODE
from specctl.epic_index import next_epic_id, read_epic_rows, write_epic_rows
from specctl.feature_index import read_feature_rows, write_feature_rows
from specctl.io_utils import now_date, now_timestamp, read_text, slugify, write_text
from specctl.models import EpicRow, FeatureRow
from specctl.oneshot_utils import (
    REQUIRED_BRIEF_SECTIONS,
    checkpoint_id,
    collect_traceability_stats,
    default_components,
    dump_json_document,
    extract_bullets,
    needs_ui_components,
    parse_brief_sections,
)
from specctl.validators.ids import FEATURE_ID_RE


def run(args) -> int:
    mode = (getattr(args, "mode", "agentic") or "agentic").strip().lower()
    if mode not in {"agentic", "deterministic"}:
        print(f"[ERROR] Invalid epic create mode: {mode}")
        return 1
    if mode == "deterministic":
        return _run_deterministic(args)
    return _run_agentic(args)


def _run_deterministic(args) -> int:
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
    write_feature_rows(features_path, working_rows, version="2.3.0")

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
    write_epic_rows(epics_path, epic_rows, version="2.3.0")

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
                "status: implementing",
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

    render_stats = collect_traceability_stats(docs, working_rows)
    render_rc = render.run(Namespace(root=str(root), check=False, stats=render_stats))
    if render_rc != 0:
        print("[ERROR] Failed to render project docs after epic creation.")
        return 1

    print(f"Created epic {epic_id} at {epic_dir}")
    print(f"Created {len(created_rows)} features in scope rooted at {root_row.feature_id}")
    return 0


def _run_agentic(args) -> int:
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

    feature_rows = read_feature_rows(features_path)
    epic_rows = read_epic_rows(epics_path) if epics_path.exists() else []

    root_feature_id = args.feature_id
    if root_feature_id and not FEATURE_ID_RE.match(root_feature_id):
        print(f"[ERROR] Invalid feature ID format: {root_feature_id}")
        return 1
    if root_feature_id and any(row.feature_id == root_feature_id for row in feature_rows):
        print(f"[ERROR] Feature ID already exists: {root_feature_id}")
        return 1

    try:
        root_row_preview = create_feature_entry(
            list(feature_rows),
            name=args.name,
            status="tasks_draft",
            owner=args.owner or "unassigned",
            parent_id="",
            feature_id=root_feature_id,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    epic_id = next_epic_id(epic_rows)
    owner = args.owner or "unassigned"
    runner = args.runner or "codex"
    research_depth = getattr(args, "research_depth", "deep") or "deep"
    interactive = is_interactive_mode(bool(getattr(args, "interactive", False)), bool(getattr(args, "no_interactive", False)))

    answers_file = Path(args.answers_file).resolve() if getattr(args, "answers_file", None) else None
    answers = load_answers_file(answers_file)

    findings = collect_repo_findings(root)
    findings.insert(
        0,
        {
            "finding_id": "FIND-BRIEF-001",
            "source": str(brief_path),
            "source_type": "brief",
            "summary": f"Epic brief baseline for {args.name.strip()}",
        },
    )

    source_refs = [finding["finding_id"] for finding in findings if finding.get("finding_id")]
    nodes = build_adaptive_nodes(
        brief_sections=sections,
        root_feature_name=args.name.strip(),
        root_feature_id=root_row_preview.feature_id,
        source_refs=source_refs,
    )

    questions = default_questions(args.name.strip(), sections)

    runner_command = resolve_runner_command(runner)
    if runner_command:
        payload = {
            "phase": "epic_create_agentic",
            "runner": runner,
            "research_depth": research_depth,
            "epic_name": args.name.strip(),
            "brief_sections": sections,
            "decomposition_nodes": nodes,
            "current_answers": answers,
        }
        normalized, err = invoke_runner(runner_command, payload, root)
        if err:
            print(f"[WARN] Runner mediation failed; using local synthesis fallback: {err}")
        elif normalized is not None:
            nodes = _merge_runner_nodes(nodes, normalized.get("decomposition_nodes", []))
            findings = _merge_runner_findings(findings, normalized.get("research_findings", []))
            questions = merge_questions(questions, normalized.get("questions", []))

    answers, pending_questions = resolve_questions(questions=questions, seed_answers=answers, interactive=interactive)
    if pending_questions:
        question_pack_path = _question_pack_path(root, args)
        write_question_pack(question_pack_path, epic_name=args.name.strip(), questions=pending_questions, answers=answers)
        print(f"[NEEDS_INPUT] Required answers missing; wrote question pack to {question_pack_path}")
        return NEEDS_INPUT_EXIT_CODE

    approval_mode = (getattr(args, "approval_mode", "two-gate") or "two-gate").strip().lower()
    if approval_mode in {"two-gate", "per-feature"}:
        approved, answers = ask_approval_gate(
            gate_id="A-AGENTIC-DECOMPOSITION",
            prompt="Approve decomposition draft",
            interactive=interactive,
            seed_answers=answers,
        )
        if not approved:
            if answers.get("A-AGENTIC-DECOMPOSITION", "").strip():
                print("[ERROR] Decomposition approval rejected.")
                return 1
            question_pack_path = _question_pack_path(root, args)
            write_question_pack(
                question_pack_path,
                epic_name=args.name.strip(),
                questions=[
                    AgenticQuestion(
                        question_id="A-AGENTIC-DECOMPOSITION",
                        text="Approve decomposition draft? answer yes/no",
                        required=True,
                        source="approval",
                    )
                ],
                answers=answers,
            )
            print(f"[NEEDS_INPUT] Missing decomposition approval; wrote question pack to {question_pack_path}")
            return NEEDS_INPUT_EXIT_CODE

    create_result = _build_agentic_feature_tree(
        base_rows=feature_rows,
        nodes=nodes,
        owner=owner,
        root_row_preview=root_row_preview,
    )
    if create_result is None:
        return 1
    working_rows, created_rows, temp_to_feature_id = create_result

    if approval_mode in {"two-gate", "per-feature"}:
        commit_prompts: list[AgenticQuestion] = []
        if approval_mode == "two-gate":
            commit_prompts.append(
                AgenticQuestion(
                    question_id="A-AGENTIC-COMMIT",
                    text="Approve final feature spec write for this epic? answer yes/no",
                    required=True,
                    source="approval",
                )
            )
        else:
            for idx, row in enumerate(created_rows, start=1):
                commit_prompts.append(
                    AgenticQuestion(
                        question_id=f"A-AGENTIC-COMMIT-{idx:03d}",
                        text=f"Approve spec write for feature {row.feature_id} ({row.name})? answer yes/no",
                        required=True,
                        source="approval",
                    )
                )
        answers, pending_commit = resolve_questions(
            questions=commit_prompts,
            seed_answers=answers,
            interactive=interactive,
        )
        if pending_commit:
            question_pack_path = _question_pack_path(root, args)
            write_question_pack(question_pack_path, epic_name=args.name.strip(), questions=pending_commit, answers=answers)
            print(f"[NEEDS_INPUT] Missing approval answers; wrote question pack to {question_pack_path}")
            return NEEDS_INPUT_EXIT_CODE
        for question in commit_prompts:
            value = answers.get(question.question_id, "").strip().lower()
            if value not in {"y", "yes", "approved", "true", "1"}:
                print(f"[ERROR] Approval rejected for {question.question_id}")
                return 1

    epic_slug = f"{epic_id}-{slugify(args.name)}"
    epic_row = EpicRow(
        epic_id=epic_id,
        name=args.name.strip(),
        status="planning",
        root_feature_id=root_row_preview.feature_id,
        epic_path=f"epics/{epic_slug}",
        owner=owner,
        aliases="[]",
    )

    working_rows.sort(key=lambda row: row.feature_id)
    write_feature_rows(features_path, working_rows, version="2.3.0")

    epic_rows.append(epic_row)
    epic_rows.sort(key=lambda row: row.epic_id)
    write_epic_rows(epics_path, epic_rows, version="2.3.0")

    for row in created_rows:
        feature_dir = (docs / row.spec_path).parent
        artifacts = synthesize_feature_artifacts(
            row=row,
            owner=owner,
            root_feature_name=args.name.strip(),
            findings=findings,
            answers=answers,
        )
        for filename, text in artifacts.items():
            write_text(feature_dir / filename, text)

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
                f"root_feature_id: {root_row_preview.feature_id}",
                f"owner: {owner}",
                "status: planning",
                f"last_updated: {now_date()}",
                "generation_mode: agentic",
                f"runner: {runner}",
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
        "root_feature_id": root_row_preview.feature_id,
        "source_mode": "adaptive_agentic",
        "scope_feature_ids": scope_feature_ids,
        "nodes": [
            {
                "feature_id": temp_to_feature_id.get(node.get("temp_id", ""), ""),
                "parent_id": temp_to_feature_id.get(node.get("parent_temp_id", ""), ""),
                "name": node.get("name", ""),
                "node_type": node.get("node_type", "capability"),
                "rationale": node.get("rationale", ""),
                "confidence": float(node.get("confidence", 0.7)),
                "source_refs": node.get("source_refs", []),
            }
            for node in nodes
        ],
        "children": _children_view(nodes, temp_to_feature_id),
        "generated_components": sorted({node.get("node_type", "capability") for node in nodes if node.get("node_type")}),
        "generation_run_id": f"GEN-{now_timestamp()}",
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

    oneshot_payload: dict[str, Any] = {
        "epic_id": epic_id,
        "root_feature_id": root_row_preview.feature_id,
        "scope_feature_ids": scope_feature_ids,
        "runner": runner,
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
        "generation_run_id": decomposition_payload["generation_run_id"],
        "approval_gates": {
            "mode": approval_mode,
            "decomposition": answers.get("A-AGENTIC-DECOMPOSITION", "yes"),
            "commit": answers.get("A-AGENTIC-COMMIT", "yes"),
        },
        "synthesis_quality_profile": {
            "minimums": AGENTIC_QUALITY_MINIMUMS,
            "research_log": "research.md",
            "requires_no_tbd_evidence": True,
            "research_depth": research_depth,
        },
    }
    if runner_command:
        oneshot_payload["runner_command"] = runner_command
    dump_json_document(epic_dir / "oneshot.yaml", oneshot_payload)

    write_agentic_artifacts(
        epic_dir,
        findings=findings,
        questions=questions,
        answers=answers,
        pending_questions=[],
        state={
            "epic_id": epic_id,
            "status": "planning_complete",
            "runner": runner,
            "research_depth": research_depth,
            "generated_at": now_timestamp(),
            "question_count": len(questions),
            "scope_feature_count": len(scope_feature_ids),
        },
    )

    dump_json_document(
        epic_dir / "memory" / "state.json",
        {
            "epic_id": epic_id,
            "status": "planned",
            "last_checkpoint": "none",
            "checkpoint_status": {cp["checkpoint_id"]: "pending" for cp in checkpoints},
        },
    )
    write_text(epic_dir / "memory" / "resume_pack.md", "# Resume Pack\n\n- Agentic epic planning completed.\n")
    write_text(epic_dir / "memory" / "decisions.md", "# Decisions\n\n- Agentic decomposition and spec synthesis completed.\n")
    write_text(epic_dir / "memory" / "open_threads.md", "# Open Threads\n\n- None\n")

    render_stats = collect_traceability_stats(docs, working_rows)
    render_rc = render.run(Namespace(root=str(root), check=False, stats=render_stats))
    if render_rc != 0:
        print("[ERROR] Failed to render project docs after epic creation.")
        return 1

    print(f"Created agentic epic {epic_id} at {epic_dir}")
    print(f"Created {len(created_rows)} features in scope rooted at {root_row_preview.feature_id}")
    print("Epic status set to planning. Run oneshot to transition to implementing.")
    return 0


def _question_pack_path(root: Path, args) -> Path:
    value = getattr(args, "question_pack_out", "")
    if value:
        return Path(value).resolve()
    return (root / "agentic-question-pack.yaml").resolve()


def _merge_runner_nodes(base_nodes: list[dict[str, Any]], candidate_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidate_nodes:
        return base_nodes

    root = base_nodes[0]
    merged: list[dict[str, Any]] = [root]
    known_temp = {root.get("temp_id", "N-ROOT")}
    for idx, node in enumerate(candidate_nodes, start=1):
        if not isinstance(node, dict):
            continue
        name = str(node.get("name", "")).strip()
        if not name:
            continue
        temp_id = str(node.get("temp_id", f"N-RUNNER-{idx:03d}")).strip() or f"N-RUNNER-{idx:03d}"
        if temp_id in known_temp:
            continue
        parent_temp = str(node.get("parent_temp_id", "N-ROOT")).strip() or "N-ROOT"
        merged.append(
            {
                "temp_id": temp_id,
                "parent_temp_id": parent_temp,
                "name": name,
                "node_type": str(node.get("node_type", "capability")),
                "rationale": str(node.get("rationale", "Runner-provided decomposition rationale.")),
                "confidence": float(node.get("confidence", 0.7)),
                "source_refs": node.get("source_refs", root.get("source_refs", [])),
            }
        )
        known_temp.add(temp_id)

    if len(merged) == 1:
        return base_nodes
    return merged


def _merge_runner_findings(base_findings: list[dict[str, str]], candidate_findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    merged = list(base_findings)
    seen_ids = {finding.get("finding_id", "") for finding in merged}
    for idx, finding in enumerate(candidate_findings, start=1):
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("finding_id", f"FIND-RUNNER-{idx:03d}")).strip() or f"FIND-RUNNER-{idx:03d}"
        if finding_id in seen_ids:
            continue
        summary = str(finding.get("summary", "")).strip()
        source = str(finding.get("source", "")).strip()
        if not summary:
            continue
        merged.append(
            {
                "finding_id": finding_id,
                "source": source or "runner",
                "source_type": str(finding.get("source_type", "web")),
                "summary": summary,
            }
        )
        seen_ids.add(finding_id)
    return merged


def _build_agentic_feature_tree(
    *,
    base_rows: list[FeatureRow],
    nodes: list[dict[str, Any]],
    owner: str,
    root_row_preview: FeatureRow,
) -> tuple[list[FeatureRow], list[FeatureRow], dict[str, str]] | None:
    if not nodes:
        print("[ERROR] Agentic decomposition produced no nodes")
        return None
    root_temp = nodes[0].get("temp_id", "N-ROOT")
    temp_to_feature_id = {root_temp: root_row_preview.feature_id}

    working_rows = list(base_rows)
    created_rows: list[FeatureRow] = []

    try:
        working_rows.append(root_row_preview)
        created_rows.append(root_row_preview)

        pending = nodes[1:]
        safety = 0
        while pending:
            safety += 1
            if safety > 10000:
                print("[ERROR] Agentic decomposition produced an unresolved parent graph")
                return None
            progressed = False
            remaining: list[dict[str, Any]] = []
            for node in pending:
                parent_temp = node.get("parent_temp_id", "")
                if parent_temp not in temp_to_feature_id:
                    remaining.append(node)
                    continue
                row = create_feature_entry(
                    working_rows,
                    name=str(node.get("name", "")).strip() or "Generated Capability",
                    status="tasks_draft",
                    owner=owner,
                    parent_id=temp_to_feature_id[parent_temp],
                )
                working_rows.append(row)
                created_rows.append(row)
                temp_to_feature_id[str(node.get("temp_id", ""))] = row.feature_id
                progressed = True
            if not progressed:
                print("[ERROR] Agentic decomposition contains parent references that cannot be resolved")
                return None
            pending = remaining
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return None

    return working_rows, created_rows, temp_to_feature_id


def _children_view(nodes: list[dict[str, Any]], temp_to_feature_id: dict[str, str]) -> list[dict[str, Any]]:
    root_temp = nodes[0].get("temp_id", "") if nodes else ""
    root_children = [node for node in nodes if node.get("parent_temp_id", "") == root_temp]
    out: list[dict[str, Any]] = []
    for node in root_children:
        temp_id = str(node.get("temp_id", ""))
        child_nodes = [item for item in nodes if item.get("parent_temp_id", "") == temp_id]
        out.append(
            {
                "feature_id": temp_to_feature_id.get(temp_id, ""),
                "name": node.get("name", ""),
                "node_type": node.get("node_type", "journey"),
                "components": [
                    {
                        "feature_id": temp_to_feature_id.get(str(child.get("temp_id", "")), ""),
                        "name": child.get("name", ""),
                        "node_type": child.get("node_type", "capability"),
                    }
                    for child in child_nodes
                ],
            }
        )
    return out
