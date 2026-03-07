from __future__ import annotations

import json

from specctl.command_utils import project_root
from specctl.validators.project import lint_project_with_impact


def run(args) -> int:
    root = project_root(args.root)
    messages, stats, oneshot_stats, impact_scan = lint_project_with_impact(root)
    errors = sum(1 for m in messages if m.severity == "ERROR")
    warnings = sum(1 for m in messages if m.severity == "WARN")

    payload = {
        "errors": errors,
        "warnings": warnings,
        "requirements_total": stats.requirements_total,
        "requirements_with_design": stats.requirements_with_design,
        "requirements_with_tasks": stats.requirements_with_tasks,
        "scenarios_total": stats.scenarios_total,
        "scenarios_with_evidence": stats.scenarios_with_evidence,
        "epics_total": oneshot_stats.epics_total,
        "runs_total": oneshot_stats.runs_total,
        "active_runs": oneshot_stats.active_runs,
        "checkpoints_passed": oneshot_stats.checkpoints_passed,
        "checkpoints_failed": oneshot_stats.checkpoints_failed,
        "blockers_opened": oneshot_stats.blockers_opened,
        "blockers_resolved": oneshot_stats.blockers_resolved,
        "placeholder_leakage_count": oneshot_stats.placeholder_leakage_count,
        "impact_suspects_open": len(impact_scan.suspects) if impact_scan is not None else 0,
        "impact_features_tracked": impact_scan.features_tracked if impact_scan is not None else 0,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Spec System Report")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 1 if errors else 0
