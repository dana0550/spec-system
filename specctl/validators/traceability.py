from __future__ import annotations

import re
from pathlib import Path

from specctl.models import LintMessage, TraceabilityStats
from specctl.validators.requirements import extract_requirement_ids, extract_scenario_ids

EVIDENCE_LINE_RE = re.compile(r"^\s*Evidence:\s*(S-F\d{3}(?:\.\d{2})*-\d{3})\b", re.MULTILINE)


def validate_feature_traceability(feature_dir: Path) -> tuple[list[LintMessage], TraceabilityStats]:
    messages: list[LintMessage] = []
    stats = TraceabilityStats()

    requirements_path = feature_dir / "requirements.md"
    design_path = feature_dir / "design.md"
    tasks_path = feature_dir / "tasks.md"
    verification_path = feature_dir / "verification.md"

    for required in [requirements_path, design_path, tasks_path, verification_path]:
        if not required.exists():
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="FILE_MISSING",
                    message=f"Missing required feature file: {required.name}",
                    path=required,
                )
            )

    if any(not p.exists() for p in [requirements_path, design_path, tasks_path, verification_path]):
        return messages, stats

    req_text = requirements_path.read_text(encoding="utf-8")
    design_text = design_path.read_text(encoding="utf-8")
    tasks_text = tasks_path.read_text(encoding="utf-8")
    verification_text = verification_path.read_text(encoding="utf-8")

    req_ids = sorted(set(extract_requirement_ids(req_text)))
    scenario_ids = sorted(set(extract_scenario_ids(req_text) + extract_scenario_ids(verification_text)))
    design_req_ids = set(extract_requirement_ids(design_text))
    task_req_ids = set(extract_requirement_ids(tasks_text))
    evidence_ids = set(EVIDENCE_LINE_RE.findall(verification_text))

    stats.requirements_total += len(req_ids)
    stats.scenarios_total += len(scenario_ids)

    for req_id in req_ids:
        if req_id in design_req_ids:
            stats.requirements_with_design += 1
        else:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="TRACE_DESIGN_MISSING",
                    message=f"Requirement {req_id} missing from design.md",
                    path=design_path,
                    )
                )

        if req_id in task_req_ids:
            stats.requirements_with_tasks += 1
        else:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="TRACE_TASK_MISSING",
                    message=f"Requirement {req_id} missing from tasks.md",
                    path=tasks_path,
                )
            )

    for scenario_id in scenario_ids:
        if scenario_id in evidence_ids:
            stats.scenarios_with_evidence += 1
        else:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="TRACE_EVIDENCE_MISSING",
                    message=f"Scenario {scenario_id} is missing evidence marker 'Evidence: {scenario_id}'",
                    path=verification_path,
                )
            )

    return messages, stats
