from __future__ import annotations

from pathlib import Path

from specctl.commands.oneshot_common import (
    load_epic_and_contract,
    read_run_state,
    write_run_state,
)
from specctl.commands.oneshot_runtime import CheckpointExecutionConfig, finalize_run_status, process_checkpoint, write_summary
from specctl.oneshot_utils import parse_blockers, write_memory_files


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
    resume_config = CheckpointExecutionConfig(
        prompt_suffix=".resume.prompt.md",
        checkpoint_event_type="checkpoint_resume",
        checkpoint_event_extra=None,
        runner_event_type="runner_resume_invocation",
        runner_fallback_output="Runner command not configured; validation-only resume.",
        repair_attempt_event_type=None,
        repair_event_type="repair_command_resume",
        validation_phase="resume",
        retry_phase="resume-retry",
        resolve_blockers_on_success=True,
        emit_checkpoint_passed_event=False,
        emit_blocker_events=False,
    )
    blocker_seq = len(parse_blockers(run_dir / "blockers.md"))

    attempted_checkpoints: set[str] = set()
    while state.get("status") in {"running", "stabilizing"}:
        progressed = False
        for checkpoint in checkpoints:
            checkpoint_id = checkpoint.get("checkpoint_id", "")
            if checkpoint_id in attempted_checkpoints:
                continue
            if state["checkpoint_status"].get(checkpoint_id) not in {
                "pending",
                "in_progress",
                "blocked_with_placeholder",
            }:
                continue
            deps = checkpoint.get("depends_on", [])
            if any(state["checkpoint_status"].get(dep) != "passed" for dep in deps):
                continue

            progressed = True
            attempted_checkpoints.add(checkpoint_id)
            blocker_seq, hard_stopped = process_checkpoint(
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
                config=resume_config,
            )
            if hard_stopped:
                break
        if not progressed:
            break

    finalize_run_status(state)

    write_run_state(run_dir, state)
    blockers = parse_blockers(run_dir / "blockers.md")
    write_memory_files(epic_dir / "memory", state, [row for row in blockers if row["status"] == "open"])
    write_summary(run_dir, state, blockers)
    print(f"Resumed one-shot run {args.run_id} for epic {epic.epic_id}")
    print(f"Run status: {state['status']}")
    return 1 if state["status"] == "blocked" else 0
