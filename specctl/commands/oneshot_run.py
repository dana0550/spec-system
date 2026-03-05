from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from specctl.commands.oneshot_common import append_event, load_epic_and_contract, run_shell, write_run_state
from specctl.constants import ONESHOT_PLACEHOLDER_PREFIX
from specctl.io_utils import now_date, now_timestamp, write_text
from specctl.oneshot_utils import (
    append_blocker,
    blocker_id,
    empty_blocker_ledger,
    new_run_id,
    parse_blockers,
    resolve_blockers_for_checkpoint,
    write_memory_files,
)


def run(args) -> int:
    root = Path(args.root).resolve()
    loaded, err = load_epic_and_contract(root, args.epic_id)
    if err:
        print(f"[ERROR] {err}")
        return 1

    epic = loaded["epic"]
    epic_dir: Path = loaded["epic_dir"]
    contract = loaded["contract"]
    checkpoints = contract.get("checkpoint_graph", [])
    if not checkpoints:
        print(f"[ERROR] oneshot.yaml has no checkpoints for {epic.epic_id}")
        return 1

    run_id = new_run_id()
    run_dir = epic_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_text(run_dir / "blockers.md", empty_blocker_ledger())
    write_text(run_dir / "summary.md", "# Run Summary\n\n")
    write_text(run_dir / "events.jsonl", "")

    runner = args.runner or contract.get("runner", "codex")
    state = {
        "epic_id": epic.epic_id,
        "run_id": run_id,
        "runner": runner,
        "status": "running",
        "started_at": now_timestamp(),
        "last_checkpoint": "none",
        "checkpoint_status": {cp["checkpoint_id"]: "pending" for cp in checkpoints},
    }
    write_run_state(run_dir, state)

    hard_stop_types = set(contract.get("blocker_policy", {}).get("hard_stop_types", []))
    repair_policy = contract.get("repair_policy", {})
    max_retries = int(repair_policy.get("max_retries_per_checkpoint", 0))
    repair_commands = repair_policy.get("commands", [])
    if not isinstance(repair_commands, list):
        repair_commands = []

    blocker_seq = 0
    while state["status"] == "running":
        progressed = False
        for checkpoint in checkpoints:
            checkpoint_id = checkpoint.get("checkpoint_id", "")
            if not checkpoint_id:
                continue
            if state["checkpoint_status"].get(checkpoint_id) != "pending":
                continue
            deps = checkpoint.get("depends_on", [])
            if any(state["checkpoint_status"].get(dep) != "passed" for dep in deps):
                continue
            progressed = True
            blocker_seq, hard_stopped = _process_checkpoint(
                run_dir=run_dir,
                root=root,
                epic=epic,
                contract=contract,
                checkpoint=checkpoint,
                checkpoint_id=checkpoint_id,
                state=state,
                repair_commands=repair_commands,
                max_retries=max_retries,
                hard_stop_types=hard_stop_types,
                blocker_seq=blocker_seq,
                prompt_suffix=".prompt.md",
                checkpoint_event_type="checkpoint_start",
                checkpoint_event_extra={"runner": runner},
                runner_event_type="runner_invocation",
                runner_fallback_output="Runner command not configured; validation-only execution.",
                repair_attempt_event_type="repair_attempt",
                repair_event_type="repair_command",
                validation_phase="primary",
                retry_phase="retry",
                resolve_blockers_on_success=False,
                emit_checkpoint_passed_event=True,
                emit_blocker_events=True,
            )
            if hard_stopped:
                break
        if not progressed:
            break

    _finalize_run_status(state)

    write_run_state(run_dir, state)
    blockers = parse_blockers(run_dir / "blockers.md")
    write_memory_files(epic_dir / "memory", state, [row for row in blockers if row["status"] == "open"])
    _write_summary(run_dir, state, blockers)

    print(f"Started one-shot run {run_id} for epic {epic.epic_id}")
    print(f"Run status: {state['status']}")
    return 1 if state["status"] == "blocked" else 0


def _process_checkpoint(
    *,
    run_dir: Path,
    root: Path,
    epic: Any,
    contract: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_id: str,
    state: dict[str, Any],
    repair_commands: list[str],
    max_retries: int,
    hard_stop_types: set[str],
    blocker_seq: int,
    prompt_suffix: str,
    checkpoint_event_type: str,
    checkpoint_event_extra: dict[str, Any] | None,
    runner_event_type: str,
    runner_fallback_output: str,
    repair_attempt_event_type: str | None,
    repair_event_type: str,
    validation_phase: str,
    retry_phase: str,
    resolve_blockers_on_success: bool,
    emit_checkpoint_passed_event: bool,
    emit_blocker_events: bool,
) -> tuple[int, bool]:
    state["checkpoint_status"][checkpoint_id] = "in_progress"
    state["last_checkpoint"] = checkpoint_id
    checkpoint_event = {"type": checkpoint_event_type, "checkpoint_id": checkpoint_id}
    if checkpoint_event_extra:
        checkpoint_event.update(checkpoint_event_extra)
    append_event(run_dir, checkpoint_event)

    prompt_path = run_dir / f"{checkpoint_id}{prompt_suffix}"
    prompt_text = _build_scoped_prompt(epic.epic_id, state["run_id"], checkpoint)
    write_text(prompt_path, prompt_text)

    runner_command = checkpoint.get("runner_command") or contract.get("runner_command")
    if isinstance(runner_command, str) and runner_command.strip():
        rc, output = run_shell(runner_command, root)
        append_event(
            run_dir,
            {
                "type": runner_event_type,
                "checkpoint_id": checkpoint_id,
                "command": runner_command,
                "prompt_path": str(prompt_path),
                "rc": rc,
                "output": output[-3000:],
            },
        )
    else:
        append_event(
            run_dir,
            {
                "type": runner_event_type,
                "checkpoint_id": checkpoint_id,
                "command": "",
                "prompt_path": str(prompt_path),
                "rc": 0,
                "output": runner_fallback_output,
            },
        )

    validation_commands = checkpoint.get("validation_commands", contract.get("validation_commands", []))
    if not isinstance(validation_commands, list):
        validation_commands = []
    success, failed_commands = _run_validation_group(
        run_dir,
        root,
        checkpoint_id,
        validation_commands,
        phase=validation_phase,
    )
    retry_count = 0
    while not success and retry_count < max_retries:
        retry_count += 1
        if repair_attempt_event_type:
            append_event(
                run_dir,
                {"type": repair_attempt_event_type, "checkpoint_id": checkpoint_id, "attempt": retry_count},
            )
        for command in repair_commands:
            rc, output = run_shell(command, root)
            append_event(
                run_dir,
                {
                    "type": repair_event_type,
                    "checkpoint_id": checkpoint_id,
                    "attempt": retry_count,
                    "command": command,
                    "rc": rc,
                    "output": output[-2000:],
                },
            )
        success, failed_commands = _run_validation_group(
            run_dir,
            root,
            checkpoint_id,
            validation_commands,
            phase=retry_phase,
        )

    if success:
        if resolve_blockers_on_success:
            resolve_blockers_for_checkpoint(run_dir / "blockers.md", checkpoint_id)
        state["checkpoint_status"][checkpoint_id] = "passed"
        if emit_checkpoint_passed_event:
            append_event(run_dir, {"type": "checkpoint_passed", "checkpoint_id": checkpoint_id})
        return blocker_seq, False

    blocker_type = checkpoint.get("blocker_type", "implementation_gap")
    task_ids = checkpoint.get("task_ids", [])
    feature_id = checkpoint.get("feature_id", epic.root_feature_id)
    blockers_path = run_dir / "blockers.md"
    existing_open = next(
        (
            row
            for row in parse_blockers(blockers_path)
            if row["checkpoint_id"] == checkpoint_id and row["status"] == "open"
        ),
        None,
    )
    if existing_open:
        current_blocker_id = existing_open["blocker_id"]
        placeholder = existing_open["placeholder_marker"] or f"{ONESHOT_PLACEHOLDER_PREFIX}{current_blocker_id}"
    else:
        blocker_seq += 1
        current_blocker_id = blocker_id(epic.epic_id, blocker_seq)
        placeholder = f"{ONESHOT_PLACEHOLDER_PREFIX}{current_blocker_id}"
        append_blocker(
            blockers_path,
            {
                "blocker_id": current_blocker_id,
                "checkpoint_id": checkpoint_id,
                "feature_id": feature_id,
                "task_id": task_ids[0] if task_ids else "",
                "severity": "high",
                "type": blocker_type,
                "placeholder_marker": placeholder,
                "owner": epic.owner,
                "exit_criteria": "Checkpoint validations pass without retries",
                "status": "open",
            },
        )

    if blocker_type in hard_stop_types or _is_repo_integrity_failure(failed_commands):
        state["checkpoint_status"][checkpoint_id] = "failed_terminal"
        state["status"] = "blocked"
        if emit_blocker_events:
            append_event(
                run_dir,
                {
                    "type": "hard_stop",
                    "checkpoint_id": checkpoint_id,
                    "blocker_id": current_blocker_id,
                    "blocker_type": blocker_type,
                },
            )
        return blocker_seq, True

    state["checkpoint_status"][checkpoint_id] = "blocked_with_placeholder"
    if emit_blocker_events:
        append_event(
            run_dir,
            {
                "type": "soft_blocker",
                "checkpoint_id": checkpoint_id,
                "blocker_id": current_blocker_id,
                "placeholder": placeholder,
            },
        )
    return blocker_seq, False


def _finalize_run_status(state: dict[str, Any]) -> None:
    if state.get("status") == "blocked":
        return
    if any(value == "blocked_with_placeholder" for value in state["checkpoint_status"].values()):
        state["status"] = "stabilizing"
    elif all(value == "passed" for value in state["checkpoint_status"].values()):
        state["status"] = "ready_to_finalize"
    else:
        state["status"] = "stabilizing"


def _run_validation_group(
    run_dir: Path,
    root: Path,
    checkpoint_id: str,
    commands: list[str],
    phase: str = "primary",
) -> tuple[bool, list[str]]:
    if not commands:
        append_event(
            run_dir,
            {"type": "validation_group", "checkpoint_id": checkpoint_id, "phase": phase, "result": "empty"},
        )
        return True, []
    group_ok = True
    failed_commands: list[str] = []
    for command in commands:
        rc, output = run_shell(command, root)
        append_event(
            run_dir,
            {
                "type": "validation_command",
                "checkpoint_id": checkpoint_id,
                "phase": phase,
                "command": command,
                "rc": rc,
                "output": output[-3000:],
            },
        )
        if rc != 0:
            group_ok = False
            failed_commands.append(command)
    return group_ok, failed_commands


def _is_repo_integrity_failure(failed_commands: list[str]) -> bool:
    for command in failed_commands:
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue
        if len(tokens) >= 2 and tokens[0] == "specctl" and tokens[1] == "check":
            return True
        if (
            len(tokens) >= 4
            and tokens[0] in {"python", "python3"}
            and tokens[1] == "-m"
            and tokens[2] == "specctl.cli"
            and tokens[3] == "check"
        ):
            return True
    return False


def _write_summary(run_dir: Path, state: dict, blockers: list[dict[str, str]]) -> None:
    status_counts: dict[str, int] = {}
    for value in state.get("checkpoint_status", {}).values():
        status_counts[value] = status_counts.get(value, 0) + 1
    lines = [
        "# Run Summary",
        "",
        f"- Date: {now_date()}",
        f"- Run ID: {state.get('run_id')}",
        f"- Status: {state.get('status')}",
        f"- Runner: {state.get('runner')}",
        f"- Last checkpoint: {state.get('last_checkpoint')}",
        f"- Open blockers: {sum(1 for row in blockers if row['status'] == 'open')}",
        "",
        "## Checkpoint Status",
    ]
    for key in sorted(status_counts):
        lines.append(f"- {key}: {status_counts[key]}")
    write_text(run_dir / "summary.md", "\n".join(lines) + "\n")


def _build_scoped_prompt(epic_id: str, run_id: str, checkpoint: dict) -> str:
    lines = [
        "# One-Shot Checkpoint Prompt",
        "",
        f"- Epic: {epic_id}",
        f"- Run: {run_id}",
        f"- Checkpoint: {checkpoint.get('checkpoint_id', '')}",
        f"- Feature: {checkpoint.get('feature_id', '')}",
        f"- Tasks: {', '.join(checkpoint.get('task_ids', []))}",
        "",
        "## Objective",
        f"- Complete checkpoint `{checkpoint.get('checkpoint_id', '')}` and satisfy mapped task IDs.",
        "",
        "## Guardrails",
        "- Preserve repository integrity.",
        "- Keep traceability links intact.",
        "- If blocked, emit placeholder marker and continue per blocker policy.",
        "",
    ]
    return "\n".join(lines)
