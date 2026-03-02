from __future__ import annotations

from specctl.models import TraceabilityStats


def render_traceability(stats: TraceabilityStats) -> str:
    req_design_pct = _ratio(stats.requirements_with_design, stats.requirements_total)
    req_tasks_pct = _ratio(stats.requirements_with_tasks, stats.requirements_total)
    scenario_evidence_pct = _ratio(stats.scenarios_with_evidence, stats.scenarios_total)

    lines = [
        "---",
        "doc_type: traceability",
        "version: 2.0.0",
        "last_rendered: TBD",
        "---",
        "# Traceability Report",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Requirements total | {stats.requirements_total} |",
        f"| Requirements linked in design | {stats.requirements_with_design} ({req_design_pct}%) |",
        f"| Requirements linked in tasks | {stats.requirements_with_tasks} ({req_tasks_pct}%) |",
        f"| Scenarios total | {stats.scenarios_total} |",
        f"| Scenarios with evidence | {stats.scenarios_with_evidence} ({scenario_evidence_pct}%) |",
        "",
    ]
    return "\n".join(lines)


def _ratio(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 0
    return int((numerator / denominator) * 100)
