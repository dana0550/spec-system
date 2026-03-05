from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from specctl.command_utils import format_message
from specctl.commands import render
from specctl.commands.oneshot_common import load_epic_and_contract, read_run_state, run_shell, write_run_state
from specctl.epic_index import read_epic_rows, write_epic_rows
from specctl.feature_index import read_feature_rows, write_feature_rows
from specctl.io_utils import now_date, set_frontmatter_value, write_text
from specctl.models import LintMessage
from specctl.oneshot_utils import (
    collect_traceability_stats,
    parse_blockers,
    scan_placeholder_markers,
    write_memory_files,
)
from specctl.validators.traceability import validate_feature_traceability


def run(args) -> int:
    root = Path(args.root).resolve()
    loaded, err = load_epic_and_contract(root, args.epic_id)
    if err:
        print(f"[ERROR] {err}")
        return 1
    epic = loaded["epic"]
    epic_dir: Path = loaded["epic_dir"]
    contract = loaded["contract"]
    run_dir = epic_dir / "runs" / args.run_id
    if not run_dir.exists():
        print(f"[ERROR] Run ID not found: {args.run_id}")
        return 1

    messages: list[LintMessage] = []
    blockers = parse_blockers(run_dir / "blockers.md")
    open_blockers = [row for row in blockers if row["status"] == "open"]
    if open_blockers:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="ONESHOT_FINALIZE_BLOCKED",
                message=f"Run has {len(open_blockers)} open blocker(s)",
                path=run_dir / "blockers.md",
            )
        )

    placeholder_hits = scan_placeholder_markers(root, exclude_prefixes=[root / "docs" / "epics"])
    if placeholder_hits:
        path, line, marker = placeholder_hits[0]
        messages.append(
            LintMessage(
                severity="ERROR",
                code="ONESHOT_FINALIZE_BLOCKED",
                message=f"Unresolved placeholder marker found ({marker or 'unknown'})",
                path=path,
                line=line,
            )
        )

    if messages:
        for message in messages:
            print(format_message(message))
        return 1

    required_finalize_commands = contract.get("finalize_gates", {}).get(
        "required_validation_commands"
    )
    finalize_commands = (
        required_finalize_commands
        if required_finalize_commands is not None
        else contract.get("validation_commands", [])
    )
    if not isinstance(finalize_commands, list):
        finalize_commands = []
    for command in finalize_commands:
        rc, output = run_shell(command, root)
        if rc != 0:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="ONESHOT_FINALIZE_BLOCKED",
                    message=f"Finalize validation failed: {command} ({output.strip()[:120]})",
                    path=run_dir / "summary.md",
                )
            )

    if messages:
        for message in messages:
            print(format_message(message))
        return 1

    feature_rows = read_feature_rows(root / "docs" / "FEATURES.md")
    feature_by_id = {row.feature_id: row for row in feature_rows}
    for feature_id in contract.get("scope_feature_ids", []):
        row = feature_by_id.get(feature_id)
        if row is None:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="ONESHOT_TRACEABILITY_INCOMPLETE",
                    message=f"Scoped feature missing: {feature_id}",
                    path=root / "docs" / "FEATURES.md",
                )
            )
            continue
        trace_messages, _ = validate_feature_traceability((root / "docs" / row.spec_path).parent)
        for trace_message in trace_messages:
            if trace_message.severity == "ERROR":
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="ONESHOT_TRACEABILITY_INCOMPLETE",
                        message=trace_message.message,
                        path=trace_message.path,
                        line=trace_message.line,
                    )
                )

    if messages:
        for message in messages:
            print(format_message(message))
        return 1

    rollback_contents: dict[Path, str | None] = {}

    def _snapshot(path: Path) -> None:
        if path in rollback_contents:
            return
        if path.exists():
            rollback_contents[path] = path.read_text(encoding="utf-8")
        else:
            rollback_contents[path] = None

    def _rollback() -> None:
        for path, original_text in rollback_contents.items():
            if original_text is None:
                if path.exists():
                    path.unlink()
            else:
                write_text(path, original_text)

    scope_set = set(contract.get("scope_feature_ids", []))
    features_path = root / "docs" / "FEATURES.md"
    epics_path = root / "docs" / "EPICS.md"
    brief_path = epic_dir / "brief.md"
    product_map_path = root / "docs" / "PRODUCT_MAP.md"
    traceability_path = root / "docs" / "TRACEABILITY.md"
    state_path = run_dir / "state.json"
    memory_dir = epic_dir / "memory"
    memory_state_path = memory_dir / "state.json"
    decisions_path = memory_dir / "decisions.md"
    open_threads_path = memory_dir / "open_threads.md"
    resume_pack_path = memory_dir / "resume_pack.md"
    finalization_path = run_dir / "finalization.md"
    try:
        # Snapshot shared finalize outputs up front so any mid-flight failure
        # can restore a fully consistent docs state.
        _snapshot(features_path)
        _snapshot(epics_path)
        _snapshot(product_map_path)
        _snapshot(traceability_path)
        _snapshot(state_path)
        _snapshot(memory_state_path)
        _snapshot(decisions_path)
        _snapshot(open_threads_path)
        _snapshot(resume_pack_path)
        _snapshot(finalization_path)
        if brief_path.exists():
            _snapshot(brief_path)

        for row in feature_rows:
            if row.feature_id in scope_set:
                row.status = "done"
                feature_dir = (root / "docs" / row.spec_path).parent
                for name in ["requirements.md", "design.md", "tasks.md", "verification.md"]:
                    path = feature_dir / name
                    if path.exists():
                        _snapshot(path)
                        set_frontmatter_value(path, "status", "done")
        write_feature_rows(features_path, feature_rows, version="2.1.0")

        epic_rows = read_epic_rows(epics_path)
        for row in epic_rows:
            if row.epic_id == epic.epic_id:
                row.status = "done"
        write_epic_rows(epics_path, epic_rows, version="2.1.0")
        if brief_path.exists():
            set_frontmatter_value(brief_path, "status", "done")

        render_stats = collect_traceability_stats(root / "docs", feature_rows)
        render_rc = render.run(Namespace(root=str(root), check=False, stats=render_stats))
        if render_rc != 0:
            raise RuntimeError("Failed to render generated docs after finalization")

        if state_path.exists():
            try:
                state = read_run_state(run_dir)
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
        else:
            state = {"checkpoint_status": {}}
        state["status"] = "completed"
        state["completed_at"] = now_date()
        write_run_state(run_dir, state)
        write_memory_files(memory_dir, state, [])

        write_text(
            finalization_path,
            "\n".join(
                [
                    "# Finalization Summary",
                    "",
                    f"- Date: {now_date()}",
                    f"- Epic ID: {epic.epic_id}",
                    f"- Run ID: {args.run_id}",
                    f"- Scoped features marked done: {len(scope_set)}",
                    "- Open blockers: 0",
                    "- Placeholder leakage: 0",
                    "",
                ]
            )
            + "\n",
        )
    except Exception as exc:
        try:
            _rollback()
        except Exception as rollback_exc:
            print(f"[ERROR] Rollback failed during finalize: {rollback_exc}")
        print(f"[ERROR] Failed to finalize run changes: {exc}")
        return 1

    print(f"Finalized one-shot run {args.run_id} for epic {epic.epic_id}")
    return 0
