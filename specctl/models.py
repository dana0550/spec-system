from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LintMessage:
    severity: str
    code: str
    message: str
    path: Optional[Path] = None
    line: Optional[int] = None


@dataclass
class FeatureRow:
    feature_id: str
    name: str
    status: str
    parent_id: str
    spec_path: str
    owner: str
    aliases: str


@dataclass
class EpicRow:
    epic_id: str
    name: str
    status: str
    root_feature_id: str
    epic_path: str
    owner: str
    aliases: str


@dataclass
class TraceabilityStats:
    requirements_total: int = 0
    requirements_with_design: int = 0
    requirements_with_tasks: int = 0
    scenarios_total: int = 0
    scenarios_with_evidence: int = 0


@dataclass
class OneShotStats:
    epics_total: int = 0
    runs_total: int = 0
    active_runs: int = 0
    checkpoints_passed: int = 0
    checkpoints_failed: int = 0
    blockers_opened: int = 0
    blockers_resolved: int = 0
    placeholder_leakage_count: int = 0
