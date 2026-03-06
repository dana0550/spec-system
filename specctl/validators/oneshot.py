from __future__ import annotations

import re
from pathlib import Path

from specctl.models import EpicRow, FeatureRow, LintMessage
from specctl.oneshot_utils import HARD_STOP_TYPES, load_json_document, parse_blockers, parse_task_ids


CHECKPOINT_ID_RE = re.compile(r"^C-E\d{3}-\d{3,}$")
BLOCKER_ID_RE = re.compile(r"^B-E\d{3}-\d{3,}$")
REQUIRED_ONESHOT_KEYS = {
    "epic_id",
    "root_feature_id",
    "scope_feature_ids",
    "runner",
    "checkpoint_graph",
    "validation_commands",
    "repair_policy",
    "blocker_policy",
    "finalize_gates",
}


def validate_oneshot_contract(
    root: Path,
    epic: EpicRow,
    feature_by_id: dict[str, FeatureRow],
) -> tuple[list[LintMessage], dict | None]:
    messages: list[LintMessage] = []
    docs = root / "docs"
    epic_dir = docs / epic.epic_path
    oneshot_path = epic_dir / "oneshot.yaml"
    payload, err = load_json_document(oneshot_path)
    if err:
        return [
            LintMessage(
                severity="ERROR",
                code="ONESHOT_CONTRACT_MISSING",
                message=err,
                path=oneshot_path,
            )
        ], None

    missing = sorted(REQUIRED_ONESHOT_KEYS - set(payload))
    if missing:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="ONESHOT_CONTRACT_MISSING",
                message=f"oneshot.yaml missing required keys: {', '.join(missing)}",
                path=oneshot_path,
            )
        )

    scope_feature_ids = payload.get("scope_feature_ids", [])
    if not isinstance(scope_feature_ids, list) or not scope_feature_ids:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="EPIC_SCOPE_FEATURE_MISSING",
                message="scope_feature_ids must be a non-empty list",
                path=oneshot_path,
            )
        )
        scope_feature_ids = []
    else:
        for feature_id in scope_feature_ids:
            if feature_id not in feature_by_id:
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="EPIC_SCOPE_FEATURE_MISSING",
                        message=f"Scope feature ID '{feature_id}' not found in FEATURES.md",
                        path=oneshot_path,
                    )
                )

    checkpoints = payload.get("checkpoint_graph", [])
    if not isinstance(checkpoints, list) or not checkpoints:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="ONESHOT_CHECKPOINT_UNMAPPED",
                message="checkpoint_graph must contain at least one checkpoint",
                path=oneshot_path,
            )
        )
        checkpoints = []

    known_task_ids = _task_ids_for_scope(docs, scope_feature_ids, feature_by_id)
    checkpoint_ids: set[str] = set()
    dependency_map: dict[str, list[str]] = {}
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_TREE_INVALID",
                    message="Each checkpoint entry must be an object",
                    path=oneshot_path,
                )
            )
            continue
        checkpoint_id = checkpoint.get("checkpoint_id", "")
        if not isinstance(checkpoint_id, str) or not CHECKPOINT_ID_RE.match(checkpoint_id):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_TREE_INVALID",
                    message=f"Invalid checkpoint ID '{checkpoint_id}'",
                    path=oneshot_path,
                )
            )
            continue
        if checkpoint_id in checkpoint_ids:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_TREE_INVALID",
                    message=f"Duplicate checkpoint ID '{checkpoint_id}'",
                    path=oneshot_path,
                )
            )
        checkpoint_ids.add(checkpoint_id)
        depends_on = checkpoint.get("depends_on", [])
        if not isinstance(depends_on, list):
            depends_on = []
        dependency_map[checkpoint_id] = [dep for dep in depends_on if isinstance(dep, str)]

        task_ids = checkpoint.get("task_ids", [])
        if not isinstance(task_ids, list) or not task_ids:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="ONESHOT_CHECKPOINT_UNMAPPED",
                    message=f"Checkpoint {checkpoint_id} must include non-empty task_ids",
                    path=oneshot_path,
                )
            )
            continue
        if not any(task_id in known_task_ids for task_id in task_ids if isinstance(task_id, str)):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="ONESHOT_CHECKPOINT_UNMAPPED",
                    message=f"Checkpoint {checkpoint_id} is not mapped to any known task ID",
                    path=oneshot_path,
                )
            )

    for checkpoint_id, depends_on in dependency_map.items():
        for dep in depends_on:
            if dep not in checkpoint_ids:
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="EPIC_TREE_INVALID",
                        message=f"Checkpoint {checkpoint_id} depends on unknown checkpoint {dep}",
                        path=oneshot_path,
                    )
                )
    if _has_cycle(dependency_map):
        messages.append(
            LintMessage(
                severity="ERROR",
                code="EPIC_TREE_INVALID",
                message="Checkpoint graph contains a dependency cycle",
                path=oneshot_path,
            )
        )

    validation_commands = payload.get("validation_commands", [])
    if not isinstance(validation_commands, list) or not validation_commands:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="ONESHOT_VALIDATION_CMD_MISSING",
                message="validation_commands must contain at least one command",
                path=oneshot_path,
            )
        )

    blocker_policy = payload.get("blocker_policy", {})
    if isinstance(blocker_policy, dict):
        hard_stop_types = blocker_policy.get("hard_stop_types", [])
        if not isinstance(hard_stop_types, list):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_TREE_INVALID",
                    message="blocker_policy.hard_stop_types must be a list",
                    path=oneshot_path,
                )
            )
        else:
            for blocker_type in hard_stop_types:
                if blocker_type not in HARD_STOP_TYPES:
                    messages.append(
                        LintMessage(
                            severity="WARN",
                            code="EPIC_TREE_INVALID",
                            message=f"Unknown blocker hard-stop type '{blocker_type}'",
                            path=oneshot_path,
                        )
                    )

    return messages, payload


def validate_run_artifacts(epic_dir: Path, run_id: str | None = None) -> list[LintMessage]:
    messages: list[LintMessage] = []
    runs_dir = epic_dir / "runs"
    if not runs_dir.exists():
        return messages
    run_dirs = sorted(path for path in runs_dir.iterdir() if path.is_dir())
    if run_id:
        run_dirs = [path for path in run_dirs if path.name == run_id]
        if not run_dirs:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="ONESHOT_BLOCKER_LEDGER_INVALID",
                    message=f"Run ID not found: {run_id}",
                    path=runs_dir,
                )
            )
            return messages
    for run_dir in run_dirs:
        blockers_path = run_dir / "blockers.md"
        if not blockers_path.exists():
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="ONESHOT_BLOCKER_LEDGER_INVALID",
                    message=f"Missing blockers ledger for {run_dir.name}",
                    path=blockers_path,
                )
            )
            continue
        for row in parse_blockers(blockers_path):
            if not BLOCKER_ID_RE.match(row["blocker_id"]):
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="ONESHOT_BLOCKER_LEDGER_INVALID",
                        message=f"Invalid blocker ID '{row['blocker_id']}' in {run_dir.name}",
                        path=blockers_path,
                    )
                )
            if row["status"] not in {"open", "resolved", "waived"}:
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="ONESHOT_BLOCKER_LEDGER_INVALID",
                        message=f"Invalid blocker status '{row['status']}' in {run_dir.name}",
                        path=blockers_path,
                    )
                )
        for required in ["events.jsonl", "summary.md", "state.json"]:
            required_path = run_dir / required
            if not required_path.exists():
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="ONESHOT_BLOCKER_LEDGER_INVALID",
                        message=f"Missing run artifact: {required}",
                        path=required_path,
                    )
                )
    return messages


def _task_ids_for_scope(
    docs: Path,
    scope_feature_ids: list[str],
    feature_by_id: dict[str, FeatureRow],
) -> set[str]:
    task_ids: set[str] = set()
    for feature_id in scope_feature_ids:
        row = feature_by_id.get(feature_id)
        if not row:
            continue
        tasks_path = (docs / row.spec_path).parent / "tasks.md"
        if not tasks_path.exists():
            continue
        task_ids.update(parse_task_ids(tasks_path.read_text(encoding="utf-8")))
    return task_ids


def _has_cycle(dependency_map: dict[str, list[str]]) -> bool:
    visited: set[str] = set()
    active: set[str] = set()

    def dfs(node: str) -> bool:
        if node in active:
            return True
        if node in visited:
            return False
        visited.add(node)
        active.add(node)
        for dep in dependency_map.get(node, []):
            if dfs(dep):
                return True
        active.remove(node)
        return False

    return any(dfs(node) for node in dependency_map)
