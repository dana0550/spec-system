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
from specctl.oneshot_utils import parse_blockers, scan_placeholder_markers, write_memory_files
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

    rollback_contents: dict[Path, str] = {}

    def _snapshot(path: Path) -> None:
        if path.exists() and path not in rollback_contents:
            rollback_contents[path] = path.read_text(encoding="utf-8")

    scope_set = set(contract.get("scope_feature_ids", []))
    for row in feature_rows:
        if row.feature_id in scope_set:
            row.status = "done"
            feature_dir = (root / "docs" / row.spec_path).parent
            for name in ["requirements.md", "design.md", "tasks.md", "verification.md"]:
                path = feature_dir / name
                if path.exists():
                    _snapshot(path)
                    set_frontmatter_value(path, "status", "done")
    features_path = root / "docs" / "FEATURES.md"
    _snapshot(features_path)
    write_feature_rows(features_path, feature_rows, version="2.1.0")

    epics_path = root / "docs" / "EPICS.md"
    epic_rows = read_epic_rows(epics_path)
    for row in epic_rows:
        if row.epic_id == epic.epic_id:
            row.status = "done"
    _snapshot(epics_path)
    write_epic_rows(epics_path, epic_rows, version="2.1.0")
    brief_path = epic_dir / "brief.md"
    if brief_path.exists():
        _snapshot(brief_path)
        set_frontmatter_value(brief_path, "status", "done")

    render_rc = render.run(Namespace(root=str(root), check=False))
    if render_rc != 0:
        for path, original_text in rollback_contents.items():
            write_text(path, original_text)
        print("[ERROR] Failed to render generated docs after finalization")
        return 1

    state_path = run_dir / "state.json"
    if state_path.exists():
        try:
            state = read_run_state(run_dir)
        except ValueError as exc:
            print(f"[ERROR] {exc}")
            return 1
    else:
        state = {"checkpoint_status": {}}
    state["status"] = "completed"
    state["completed_at"] = now_date()
    write_run_state(run_dir, state)
    write_memory_files(epic_dir / "memory", state, [])

    write_text(
        run_dir / "finalization.md",
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
    print(f"Finalized one-shot run {args.run_id} for epic {epic.epic_id}")
    return 0
