from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from specctl.constants import ONESHOT_PLACEHOLDER_PREFIX
from specctl.io_utils import escape_markdown_table_cell, now_date, now_timestamp, split_markdown_table_row, write_text


REQUIRED_BRIEF_SECTIONS = ["Vision", "Outcomes", "User Journeys", "Constraints", "Non-Goals"]
UI_KEYWORDS = {"ui", "frontend", "screen", "workflow", "form", "dashboard"}
HARD_STOP_TYPES = [
    "data_loss_risk",
    "security_vulnerability",
    "destructive_migration_without_rollback",
    "compliance_privacy_breach",
    "broken_repository_integrity",
]
BLOCKER_HEADER = (
    "| Blocker ID | Checkpoint ID | Feature ID | Task ID | Severity | Type | "
    "Placeholder Marker | Owner | Exit Criteria | Status |"
)
BLOCKER_RULE = "|---|---|---|---|---|---|---|---|---|---|"
PLACEHOLDER_RE = re.compile(rf"{re.escape(ONESHOT_PLACEHOLDER_PREFIX)}(B-E\d{{3}}-\d{{3}})")


def load_json_document(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"Missing file: {path}"
    try:
        raw = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        return None, f"Invalid JSON/YAML payload in {path}: {exc}"
    if not isinstance(data, dict):
        return None, f"Expected object at root in {path}"
    return data, None


def dump_json_document(path: Path, payload: dict[str, Any]) -> None:
    if path.suffix in {".yaml", ".yml"}:
        text = yaml.safe_dump(payload, sort_keys=True, allow_unicode=False)
    else:
        text = json.dumps(payload, indent=2, sort_keys=True)
    write_text(path, text.rstrip("\n") + "\n")


def parse_brief_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def extract_bullets(section_text: str) -> list[str]:
    bullets: list[str] = []
    for line in section_text.splitlines():
        match = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if match:
            bullets.append(match.group(1).strip())
    return bullets


def needs_ui_components(text: str) -> bool:
    lower = text.lower()
    for keyword in UI_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lower):
            return True
    return False


def default_components(include_ui: bool) -> list[str]:
    components = ["Contract/API", "Domain/Data", "Execution/Integration", "Verification/Observability"]
    if include_ui:
        components.append("UX/Client")
    return components


def checkpoint_id(epic_id: str, idx: int) -> str:
    return f"C-{epic_id.replace('-', '')}-{idx:03d}"


def blocker_id(epic_id: str, idx: int) -> str:
    return f"B-{epic_id.replace('-', '')}-{idx:03d}"


def new_run_id() -> str:
    return f"RUN-{now_timestamp()}"


def empty_blocker_ledger() -> str:
    return "\n".join(["# Blockers Ledger", "", BLOCKER_HEADER, BLOCKER_RULE, ""]) + "\n"


def parse_blockers(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        if line.strip() in {BLOCKER_HEADER, BLOCKER_RULE}:
            continue
        cols = split_markdown_table_row(line.strip().strip("|"))
        if len(cols) != 10 or not cols[0].startswith("B-"):
            continue
        rows.append(
            {
                "blocker_id": cols[0],
                "checkpoint_id": cols[1],
                "feature_id": cols[2],
                "task_id": cols[3],
                "severity": cols[4],
                "type": cols[5],
                "placeholder_marker": cols[6],
                "owner": cols[7],
                "exit_criteria": cols[8],
                "status": cols[9],
            }
        )
    return rows


def append_blocker(path: Path, row: dict[str, str]) -> None:
    if not path.exists():
        write_text(path, empty_blocker_ledger())
    line = (
        f"| {escape_markdown_table_cell(row['blocker_id'])} | {escape_markdown_table_cell(row['checkpoint_id'])} | "
        f"{escape_markdown_table_cell(row['feature_id'])} | {escape_markdown_table_cell(row['task_id'])} | {escape_markdown_table_cell(row['severity'])} | "
        f"{escape_markdown_table_cell(row['type'])} | {escape_markdown_table_cell(row['placeholder_marker'])} | {escape_markdown_table_cell(row['owner'])} | "
        f"{escape_markdown_table_cell(row['exit_criteria'])} | {escape_markdown_table_cell(row['status'])} |"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def resolve_blockers_for_checkpoint(path: Path, checkpoint_id: str) -> int:
    if not path.exists():
        return 0

    updated = 0
    rewritten_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        rewritten = line
        if line.startswith("|"):
            stripped = line.strip()
            if stripped not in {BLOCKER_HEADER, BLOCKER_RULE}:
                cols = split_markdown_table_row(stripped.strip("|"))
                if len(cols) == 10 and cols[0].startswith("B-"):
                    if cols[1] == checkpoint_id and cols[9] == "open":
                        cols[9] = "resolved"
                        updated += 1
                    rewritten = f"| {' | '.join(escape_markdown_table_cell(col) for col in cols)} |"
        rewritten_lines.append(rewritten)

    if updated:
        write_text(path, "\n".join(rewritten_lines) + "\n")
    return updated


def collect_run_stats(runs_dir: Path) -> dict[str, int]:
    totals = {
        "runs_total": 0,
        "active_runs": 0,
        "checkpoints_passed": 0,
        "checkpoints_failed": 0,
        "blockers_opened": 0,
        "blockers_resolved": 0,
    }
    if not runs_dir.exists():
        return totals

    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        totals["runs_total"] += 1
        state_path = run_dir / "state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {}
            if state.get("status") in {"running", "stabilizing"}:
                totals["active_runs"] += 1
            checkpoint_status = state.get("checkpoint_status", {})
            if isinstance(checkpoint_status, dict):
                totals["checkpoints_passed"] += sum(1 for value in checkpoint_status.values() if value == "passed")
                totals["checkpoints_failed"] += sum(
                    1 for value in checkpoint_status.values() if value in {"failed_terminal", "blocked_with_placeholder"}
                )

        for blocker in parse_blockers(run_dir / "blockers.md"):
            totals["blockers_opened"] += 1
            if blocker["status"] == "resolved":
                totals["blockers_resolved"] += 1
    return totals


def write_memory_files(memory_dir: Path, state: dict[str, Any], open_blockers: list[dict[str, str]]) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    state_path = memory_dir / "state.json"
    decisions_path = memory_dir / "decisions.md"
    open_threads_path = memory_dir / "open_threads.md"
    resume_path = memory_dir / "resume_pack.md"

    dump_json_document(state_path, state)

    existing_decisions = []
    if decisions_path.exists():
        existing_decisions = decisions_path.read_text(encoding="utf-8").splitlines()
    decision_line = f"- {now_date()}: checkpoint={state.get('last_checkpoint', 'none')} status={state.get('status', '')}"
    decision_entries = [line for line in existing_decisions if line.startswith("- ")]
    decision_entries.insert(0, decision_line)
    decision_entries = decision_entries[:40]
    decisions_text = "# Decisions\n\n" + ("\n".join(decision_entries) + "\n" if decision_entries else "")
    write_text(decisions_path, decisions_text)

    open_lines = ["# Open Threads", ""]
    if not open_blockers:
        open_lines.append("- None")
    else:
        for blocker in open_blockers:
            open_lines.append(
                f"- {blocker['blocker_id']} ({blocker['type']}): {blocker['exit_criteria']} "
                f"[feature={blocker['feature_id']}, checkpoint={blocker['checkpoint_id']}]"
            )
    write_text(open_threads_path, "\n".join(open_lines) + "\n")

    checkpoint_status = state.get("checkpoint_status", {})
    pending = sorted([key for key, value in checkpoint_status.items() if value == "pending"])
    next_checkpoint = pending[0] if pending else "none"
    body = [
        "# Resume Pack",
        "",
        f"- Epic ID: {state.get('epic_id')}",
        f"- Run ID: {state.get('run_id')}",
        f"- Runner: {state.get('runner')}",
        f"- Status: {state.get('status')}",
        f"- Last checkpoint: {state.get('last_checkpoint', 'none')}",
        f"- Next checkpoint: {next_checkpoint}",
        f"- Open blockers: {len(open_blockers)}",
        "",
        "## Key points",
    ]
    for key in sorted(checkpoint_status):
        body.append(f"- {key}: {checkpoint_status[key]}")
    resume_text = "\n".join(body) + "\n"
    # Keep memory compact and deterministic for resumes.
    resume_text = "\n".join(resume_text.splitlines()[:180]) + "\n"
    if len(resume_text) > 6000:
        resume_text = resume_text[:5999] + "\n"
    write_text(resume_path, resume_text)


def scan_placeholder_markers(root: Path, exclude_prefixes: list[Path] | None = None) -> list[tuple[Path, int, str]]:
    excludes = [path.resolve() for path in (exclude_prefixes or [])]
    hits: list[tuple[Path, int, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        resolved = path.resolve()
        if any(resolved.is_relative_to(prefix) for prefix in excludes):  # type: ignore[attr-defined]
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if ONESHOT_PLACEHOLDER_PREFIX in line:
                match = PLACEHOLDER_RE.search(line)
                marker = match.group(1) if match else ""
                hits.append((path, idx, marker))
    return hits


def parse_task_ids(text: str) -> list[str]:
    return re.findall(r"\bT-F\d{3}(?:\.\d{2})*-\d{3}\b", text)
