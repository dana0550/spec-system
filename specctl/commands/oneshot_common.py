from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from specctl.epic_index import read_epic_rows
from specctl.oneshot_utils import dump_json_document, load_json_document


def load_epic_and_contract(root: Path, epic_id: str) -> tuple[dict[str, Any], str | None]:
    docs = root / "docs"
    epics = read_epic_rows(docs / "EPICS.md")
    epic = next((row for row in epics if row.epic_id == epic_id), None)
    if epic is None:
        return {}, f"Epic ID not found: {epic_id}"
    epic_dir = docs / epic.epic_path
    if not epic_dir.exists():
        return {}, f"Epic path missing: {epic.epic_path}"
    contract, err = load_json_document(epic_dir / "oneshot.yaml")
    if err:
        return {}, err
    return {"epic": epic, "epic_dir": epic_dir, "contract": contract}, None


def append_event(run_dir: Path, payload: dict[str, Any]) -> None:
    events_path = run_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def run_shell(command: str, root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=root,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode, (proc.stdout or "")


def read_run_state(run_dir: Path) -> dict[str, Any]:
    state_path = run_dir / "state.json"
    payload, err = load_json_document(state_path)
    if err:
        raise ValueError(err)
    return payload


def write_run_state(run_dir: Path, payload: dict[str, Any]) -> None:
    dump_json_document(run_dir / "state.json", payload)
