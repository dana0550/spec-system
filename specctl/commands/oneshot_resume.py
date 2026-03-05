from __future__ import annotations

from pathlib import Path

from specctl.commands.oneshot_common import (
    append_event,
    load_epic_and_contract,
    read_run_state,
    run_shell,
    write_run_state,
)
from specctl.commands.oneshot_run import _build_scoped_prompt, _is_repo_integrity_failure, _run_validation_group, _write_summary
from specctl.constants import ONESHOT_PLACEHOLDER_PREFIX
from specctl.io_utils import write_text
from specctl.oneshot_utils import append_blocker, blocker_id, parse_blockers, write_memory_files


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

    state_path = run_dir / "state.json"
    if not state_path.exists():
        print(f"[ERROR] Missing run state: {state_path}")
        return 1

    try:
        state = read_run_state(run_dir)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1
    status = state.get("status")
    if status == "blocked":
        print(f"[ERROR] Run {args.run_id} is hard-blocked and cannot resume")
        return 1
    if status not in {"running", "stabilizing"}:
        print(f"[ERROR] Run {args.run_id} is not resumable from status '{state.get('status')}'")
        return 1

    checkpoints = contract.get("checkpoint_graph", [])
    hard_stop_types = set(contract.get("blocker_policy", {}).get("hard_stop_types", []))
    repair_policy = contract.get("repair_policy", {})
    max_retries = int(repair_policy.get("max_retries_per_checkpoint", 0))
    repair_commands = repair_policy.get("commands", [])
    if not isinstance(repair_commands, list):
        repair_commands = []
    blocker_seq = len(parse_blockers(run_dir / "blockers.md"))

    for checkpoint in checkpoints:
        checkpoint_id = checkpoint.get("checkpoint_id", "")
        if state["checkpoint_status"].get(checkpoint_id) not in {"pending", "blocked_with_placeholder"}:
            continue
        deps = checkpoint.get("depends_on", [])
        if any(state["checkpoint_status"].get(dep) != "passed" for dep in deps):
            continue
        state["checkpoint_status"][checkpoint_id] = "in_progress"
        state["last_checkpoint"] = checkpoint_id
        append_event(run_dir, {"type": "checkpoint_resume", "checkpoint_id": checkpoint_id})
        prompt_path = run_dir / f"{checkpoint_id}.resume.prompt.md"
        prompt_text = _build_scoped_prompt(epic.epic_id, state["run_id"], checkpoint)
        write_text(prompt_path, prompt_text)
        runner_command = checkpoint.get("runner_command") or contract.get("runner_command")
        if isinstance(runner_command, str) and runner_command.strip():
            rc, output = run_shell(runner_command, root)
            append_event(
                run_dir,
                {
                    "type": "runner_resume_invocation",
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
                    "type": "runner_resume_invocation",
                    "checkpoint_id": checkpoint_id,
                    "command": "",
                    "prompt_path": str(prompt_path),
                    "rc": 0,
                    "output": "Runner command not configured; validation-only resume.",
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
            phase="resume",
        )
        retry_count = 0
        while not success and retry_count < max_retries:
            retry_count += 1
            for command in repair_commands:
                rc, output = run_shell(command, root)
                append_event(
                    run_dir,
                    {
                        "type": "repair_command_resume",
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
                phase="resume-retry",
            )

        if success:
            state["checkpoint_status"][checkpoint_id] = "passed"
            continue

        blocker_seq += 1
        current_blocker_id = blocker_id(epic.epic_id, blocker_seq)
        placeholder = f"{ONESHOT_PLACEHOLDER_PREFIX}{current_blocker_id}"
        blocker_type = checkpoint.get("blocker_type", "implementation_gap")
        task_ids = checkpoint.get("task_ids", [])
        feature_id = checkpoint.get("feature_id", epic.root_feature_id)
        append_blocker(
            run_dir / "blockers.md",
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
            break
        state["checkpoint_status"][checkpoint_id] = "blocked_with_placeholder"

    if state.get("status") != "blocked":
        if any(value == "blocked_with_placeholder" for value in state["checkpoint_status"].values()):
            state["status"] = "stabilizing"
        elif all(value == "passed" for value in state["checkpoint_status"].values()):
            state["status"] = "ready_to_finalize"
        else:
            state["status"] = "stabilizing"

    write_run_state(run_dir, state)
    blockers = parse_blockers(run_dir / "blockers.md")
    write_memory_files(epic_dir / "memory", state, [row for row in blockers if row["status"] == "open"])
    _write_summary(run_dir, state, blockers)
    print(f"Resumed one-shot run {args.run_id} for epic {epic.epic_id}")
    print(f"Run status: {state['status']}")
    return 1 if state["status"] == "blocked" else 0
