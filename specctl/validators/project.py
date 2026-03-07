from __future__ import annotations

from pathlib import Path

from specctl.constants import REQUIRED_DOC_FILES
from specctl.feature_index import read_feature_rows
from specctl.impact import build_lint_messages, scan_impact
from specctl.models import FeatureRow, LintMessage, OneShotStats, TraceabilityStats
from specctl.validators.epics import validate_epics
from specctl.validators.ids import validate_feature_ids
from specctl.validators.lifecycle import validate_statuses
from specctl.validators.requirements import validate_requirements_file
from specctl.validators.traceability import validate_feature_traceability


def lint_project(root: Path) -> tuple[list[LintMessage], TraceabilityStats, OneShotStats]:
    messages: list[LintMessage] = []
    stats = TraceabilityStats()
    oneshot_stats = OneShotStats()

    docs_dir = root / "docs"
    if not docs_dir.exists():
        messages.append(LintMessage("ERROR", "DOCS_MISSING", "docs/ directory is missing", docs_dir))
        return messages, stats, oneshot_stats

    for required in sorted(REQUIRED_DOC_FILES):
        required_path = docs_dir / required
        if not required_path.exists():
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="DOC_MISSING",
                    message=f"Missing required docs file: {required}",
                    path=required_path,
                )
            )

    features_index_path = docs_dir / "FEATURES.md"
    rows = read_feature_rows(features_index_path)
    if not rows:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="FEATURES_EMPTY",
                message="No feature rows found in docs/FEATURES.md",
                path=features_index_path,
            )
        )
    else:
        messages.extend(validate_feature_ids(rows))
        messages.extend(validate_statuses(rows))
        row_ids = {row.feature_id for row in rows}
        for row in rows:
            if row.parent_id and row.parent_id not in row_ids:
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="PARENT_MISSING",
                        message=f"Parent ID '{row.parent_id}' does not exist for {row.feature_id}",
                        path=features_index_path,
                    )
                )
            if row.parent_id == row.feature_id:
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="PARENT_SELF",
                        message=f"Feature {row.feature_id} cannot parent itself",
                        path=features_index_path,
                    )
                )
        messages.extend(validate_feature_hierarchy(rows, features_index_path))

    epic_messages, oneshot_stats = validate_epics(root, rows)
    messages.extend(epic_messages)

    features_root = docs_dir / "features"
    if not features_root.exists():
        messages.append(
            LintMessage(
                severity="ERROR",
                code="FEATURES_DIR_MISSING",
                message="docs/features directory is missing",
                path=features_root,
            )
        )
        return messages, stats, oneshot_stats

    expected_feature_dirs: set[Path] = set()
    for row in rows:
        req_path = docs_dir / row.spec_path
        if not req_path.exists():
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="SPEC_PATH_MISSING",
                    message=f"Spec path for {row.feature_id} is missing: {row.spec_path}",
                    path=req_path,
                )
            )
            continue

        feature_dir = req_path.parent.resolve()
        expected_feature_dirs.add(feature_dir)

        messages.extend(validate_requirements_file(req_path))
        trace_msgs, trace_stats = validate_feature_traceability(feature_dir)
        messages.extend(trace_msgs)
        stats.requirements_total += trace_stats.requirements_total
        stats.requirements_with_design += trace_stats.requirements_with_design
        stats.requirements_with_tasks += trace_stats.requirements_with_tasks
        stats.scenarios_total += trace_stats.scenarios_total
        stats.scenarios_with_evidence += trace_stats.scenarios_with_evidence

    for feature_dir in sorted(p for p in features_root.iterdir() if p.is_dir()):
        if feature_dir.resolve() not in expected_feature_dirs:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="FEATURE_DIR_ORPHAN",
                    message=f"Feature directory has no matching FEATURES.md row: {feature_dir.name}",
                    path=feature_dir,
                )
            )

    impact_scan = scan_impact(root)
    messages.extend(build_lint_messages(root, impact_scan))

    return messages, stats, oneshot_stats


def validate_feature_hierarchy(rows: list[FeatureRow], features_index_path: Path) -> list[LintMessage]:
    messages: list[LintMessage] = []
    if not rows:
        return messages

    row_ids = {row.feature_id for row in rows}
    children_by_parent: dict[str, set[str]] = {}
    parent_by_id = {row.feature_id: row.parent_id for row in rows}
    for row in rows:
        children_by_parent.setdefault(row.parent_id, set()).add(row.feature_id)

    roots = sorted(fid for fid, parent in parent_by_id.items() if parent == "")
    if not roots:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="HIERARCHY_NO_ROOT",
                message="No top-level feature roots found (rows with empty parent ID)",
                path=features_index_path,
            )
        )

    reachable: set[str] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        stack.extend(sorted(children_by_parent.get(node, set())))

    for feature_id in sorted(row_ids - reachable):
        messages.append(
            LintMessage(
                severity="ERROR",
                code="HIERARCHY_UNREACHABLE",
                message=f"Feature {feature_id} is not reachable from any top-level root",
                path=features_index_path,
            )
        )

    cycle_keys: set[tuple[str, ...]] = set()
    for feature_id in sorted(row_ids):
        seen_chain: list[str] = []
        seen_set: set[str] = set()
        cursor = feature_id
        while cursor in row_ids and cursor not in seen_set:
            seen_chain.append(cursor)
            seen_set.add(cursor)
            parent = parent_by_id.get(cursor, "")
            if parent == "" or parent not in row_ids:
                cursor = ""
                break
            cursor = parent
        if cursor and cursor in seen_set:
            cycle_start = seen_chain.index(cursor)
            cycle = seen_chain[cycle_start:] + [cursor]
            cycle_loop = cycle[:-1]
            rotations = [tuple(cycle_loop[i:] + cycle_loop[:i]) for i in range(len(cycle_loop))]
            cycle_key = min(rotations)
            if cycle_key in cycle_keys:
                continue
            cycle_keys.add(cycle_key)
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="HIERARCHY_CYCLE",
                    message=f"Hierarchy cycle detected: {' -> '.join(cycle_key + (cycle_key[0],))}",
                    path=features_index_path,
                )
            )

    return messages
