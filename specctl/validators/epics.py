from __future__ import annotations

import re
from pathlib import Path

from specctl.agentic_epic import validate_feature_quality
from specctl.constants import EPIC_STATUSES
from specctl.epic_index import read_epic_rows
from specctl.models import FeatureRow, LintMessage, OneShotStats
from specctl.oneshot_utils import collect_run_stats, scan_placeholder_markers
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

        oneshot_msgs, payload = validate_oneshot_contract(root, row, feature_by_id)
        messages.extend(oneshot_msgs)
        if payload:
            messages.extend(_validate_agentic_profile(root, row, payload, feature_by_id))

        messages.extend(validate_run_artifacts(epic_dir))
        run_stats = collect_run_stats(epic_dir / "runs")
        stats.runs_total += run_stats["runs_total"]
        stats.active_runs += run_stats["active_runs"]
        stats.checkpoints_passed += run_stats["checkpoints_passed"]
        stats.checkpoints_failed += run_stats["checkpoints_failed"]
        stats.blockers_opened += run_stats["blockers_opened"]
        stats.blockers_resolved += run_stats["blockers_resolved"]

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


def _validate_agentic_profile(
    root: Path,
    epic_row,
    payload: dict,
    feature_by_id: dict[str, FeatureRow],
) -> list[LintMessage]:
    messages: list[LintMessage] = []
    profile = payload.get("synthesis_quality_profile")
    if not isinstance(profile, dict):
        return messages

    docs = root / "docs"
    epic_dir = docs / epic_row.epic_path
    research_log = profile.get("research_log", "research.md")
    research_path = epic_dir / str(research_log)
    if not research_path.exists():
        messages.append(
            LintMessage(
                severity="ERROR",
                code="AGENTIC_RESEARCH_LOG_MISSING",
                message=f"Research log missing for agentic epic: {research_log}",
                path=research_path,
            )
        )
    else:
        text = research_path.read_text(encoding="utf-8")
        if "| Finding ID | Source | Type | Summary |" not in text:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="AGENTIC_RESEARCH_LOG_INVALID",
                    message="Research log must include canonical findings table header",
                    path=research_path,
                )
            )

    for feature_id in payload.get("scope_feature_ids", []):
        row = feature_by_id.get(feature_id)
        if row is None:
            continue
        feature_dir = (docs / row.spec_path).parent
        issues = validate_feature_quality(feature_dir)
        for issue in issues:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="AGENTIC_SPEC_QUALITY",
                    message=f"{feature_id}: {issue}",
                    path=feature_dir,
                )
            )
    return messages
