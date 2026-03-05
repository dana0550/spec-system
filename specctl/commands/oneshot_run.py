from __future__ import annotations

from pathlib import Path

from specctl.commands.oneshot_common import load_epic_and_contract, write_run_state
from specctl.commands.oneshot_runtime import finalize_run_status, process_checkpoint, write_summary
from specctl.io_utils import now_timestamp, write_text
from specctl.oneshot_utils import empty_blocker_ledger, new_run_id, parse_blockers, write_memory_files


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

    finalize_run_status(state)

    write_run_state(run_dir, state)
    blockers = parse_blockers(run_dir / "blockers.md")
    write_memory_files(epic_dir / "memory", state, [row for row in blockers if row["status"] == "open"])
    write_summary(run_dir, state, blockers)

    print(f"Started one-shot run {run_id} for epic {epic.epic_id}")
    print(f"Run status: {state['status']}")
    return 1 if state["status"] == "blocked" else 0
