from __future__ import annotations

from pathlib import Path

from specctl.constants import REQUIRED_DOC_FILES
from specctl.feature_index import read_feature_rows
from specctl.models import LintMessage, TraceabilityStats
from specctl.validators.ids import validate_feature_ids
from specctl.validators.lifecycle import validate_statuses
from specctl.validators.requirements import validate_requirements_file
from specctl.validators.traceability import validate_feature_traceability


def lint_project(root: Path) -> tuple[list[LintMessage], TraceabilityStats]:
    messages: list[LintMessage] = []
    stats = TraceabilityStats()

    docs_dir = root / "docs"
    if not docs_dir.exists():
        messages.append(LintMessage("ERROR", "DOCS_MISSING", "docs/ directory is missing", docs_dir))
        return messages, stats

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
        return messages, stats

    for feature_dir in sorted(p for p in features_root.iterdir() if p.is_dir()):
        messages.extend(validate_requirements_file(feature_dir / "requirements.md"))
        trace_msgs, trace_stats = validate_feature_traceability(feature_dir)
        messages.extend(trace_msgs)
        stats.requirements_total += trace_stats.requirements_total
        stats.requirements_with_design += trace_stats.requirements_with_design
        stats.requirements_with_tasks += trace_stats.requirements_with_tasks
        stats.scenarios_total += trace_stats.scenarios_total
        stats.scenarios_with_evidence += trace_stats.scenarios_with_evidence

    return messages, stats
