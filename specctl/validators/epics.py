from __future__ import annotations

import json
import re
from pathlib import Path

from specctl.constants import EPIC_STATUSES
from specctl.epic_index import read_epic_rows
from specctl.models import FeatureRow, LintMessage, OneShotStats
from specctl.oneshot_utils import parse_blockers, scan_placeholder_markers
from specctl.validators.oneshot import validate_oneshot_contract, validate_run_artifacts


EPIC_ID_RE = re.compile(r"^E-\d{3}$")


def validate_epics(root: Path, feature_rows: list[FeatureRow]) -> tuple[list[LintMessage], OneShotStats]:
    messages: list[LintMessage] = []
    stats = OneShotStats()
    docs = root / "docs"
    epics_index = docs / "EPICS.md"
    epics_dir = docs / "epics"

    if not epics_index.exists():
        if epics_dir.exists() and any(path.is_dir() for path in epics_dir.iterdir()):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_INDEX_MISSING",
                    message="docs/epics exists but docs/EPICS.md is missing",
                    path=epics_index,
                )
            )
        return messages, stats

    rows = read_epic_rows(epics_index)
    seen: set[str] = set()
    feature_by_id = {row.feature_id: row for row in feature_rows}
    for row in rows:
        stats.epics_total += 1
        if row.epic_id in seen:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_ID_DUPLICATE",
                    message=f"Duplicate epic ID: {row.epic_id}",
                    path=epics_index,
                )
            )
        seen.add(row.epic_id)

        if not EPIC_ID_RE.match(row.epic_id):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_TREE_INVALID",
                    message=f"Invalid epic ID format: {row.epic_id}",
                    path=epics_index,
                )
            )
        if row.status not in EPIC_STATUSES:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_TREE_INVALID",
                    message=f"Invalid epic status '{row.status}' for {row.epic_id}",
                    path=epics_index,
                )
            )
        if row.root_feature_id not in feature_by_id:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_ROOT_FEATURE_MISSING",
                    message=f"Root feature '{row.root_feature_id}' missing for epic {row.epic_id}",
                    path=epics_index,
                )
            )

        epic_dir = docs / row.epic_path
        if not epic_dir.exists():
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="EPIC_TREE_INVALID",
                    message=f"Epic path missing: {row.epic_path}",
                    path=epic_dir,
                )
            )
            continue

        for required in ["brief.md", "decomposition.yaml", "oneshot.yaml", "memory", "runs"]:
            required_path = epic_dir / required
            if not required_path.exists():
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="ONESHOT_CONTRACT_MISSING",
                        message=f"Epic artifact missing: {required}",
                        path=required_path,
                    )
                )

        oneshot_msgs, contract = validate_oneshot_contract(root, row, feature_by_id)
        messages.extend(oneshot_msgs)

        messages.extend(validate_run_artifacts(epic_dir))
        _aggregate_run_stats(epic_dir, stats)

        if contract is None:
            continue

    placeholder_hits = scan_placeholder_markers(root, exclude_prefixes=[docs / "epics"])
    stats.placeholder_leakage_count += len(placeholder_hits)
    if placeholder_hits:
        path, line, marker = placeholder_hits[0]
        marker_text = marker or "unknown"
        messages.append(
            LintMessage(
                severity="ERROR",
                code="ONESHOT_PLACEHOLDER_UNTRACKED",
                message=f"Unresolved placeholder marker detected ({marker_text})",
                path=path,
                line=line,
            )
        )

    return messages, stats


def _aggregate_run_stats(epic_dir: Path, stats: OneShotStats) -> None:
    runs_dir = epic_dir / "runs"
    if not runs_dir.exists():
        return
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        state_path = run_dir / "state.json"
        if state_path.exists():
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            status = payload.get("status", "")
            if status in {"running", "stabilizing"}:
                stats.active_runs += 1
            checkpoint_status = payload.get("checkpoint_status", {})
            if isinstance(checkpoint_status, dict):
                stats.checkpoints_passed += sum(1 for value in checkpoint_status.values() if value == "passed")
                stats.checkpoints_failed += sum(
                    1 for value in checkpoint_status.values() if value in {"failed_terminal", "blocked_with_placeholder"}
                )
        blockers_path = run_dir / "blockers.md"
        for blocker in parse_blockers(blockers_path):
            if blocker["status"] == "open":
                stats.blockers_opened += 1
            if blocker["status"] == "resolved":
                stats.blockers_resolved += 1
