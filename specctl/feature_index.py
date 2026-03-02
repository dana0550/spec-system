from __future__ import annotations

import re
from pathlib import Path

from specctl.io_utils import now_date, read_text, write_text
from specctl.models import FeatureRow


TABLE_HEADER = "| ID | Name | Status | Parent ID | Spec Path | Owner | Aliases |"
TABLE_RULE = "|----|------|--------|-----------|-----------|-------|---------|"


def _escape_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", r"\|")


def _split_row_cells(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    idx = 0
    while idx < len(line):
        char = line[idx]
        if char == "\\" and idx + 1 < len(line) and line[idx + 1] in {"\\", "|"}:
            current.append(line[idx + 1])
            idx += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            idx += 1
            continue
        current.append(char)
        idx += 1
    cells.append("".join(current).strip())
    return cells


def read_feature_rows(path: Path) -> list[FeatureRow]:
    if not path.exists():
        return []
    text = read_text(path)
    rows: list[FeatureRow] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        if line.strip() in {TABLE_HEADER, TABLE_RULE}:
            continue
        parts = _split_row_cells(line.strip().strip("|"))
        if len(parts) < 7:
            continue
        if not parts[0].startswith("F-"):
            continue
        rows.append(
            FeatureRow(
                feature_id=parts[0],
                name=parts[1],
                status=parts[2],
                parent_id=parts[3],
                spec_path=parts[4],
                owner=parts[5],
                aliases=parts[6],
            )
        )
    return rows


def write_feature_rows(path: Path, rows: list[FeatureRow], version: str = "2.0.0") -> None:
    lines = [
        "---",
        "doc_type: feature_index",
        f"version: {version}",
        f"last_synced: {now_date()}",
        "---",
        "# Features Index",
        "",
        TABLE_HEADER,
        TABLE_RULE,
    ]
    for row in rows:
        lines.append(
            "| "
            f"{_escape_cell(row.feature_id)} | "
            f"{_escape_cell(row.name)} | "
            f"{_escape_cell(row.status)} | "
            f"{_escape_cell(row.parent_id)} | "
            f"{_escape_cell(row.spec_path)} | "
            f"{_escape_cell(row.owner)} | "
            f"{_escape_cell(row.aliases)} |"
        )
    lines.append("")
    write_text(path, "\n".join(lines))


def next_top_level_id(rows: list[FeatureRow]) -> str:
    nums = []
    for row in rows:
        if "." in row.feature_id:
            continue
        match = re.match(r"F-(\d{3})$", row.feature_id)
        if match:
            nums.append(int(match.group(1)))
    nxt = max(nums, default=0) + 1
    return f"F-{nxt:03d}"


def next_child_id(rows: list[FeatureRow], parent_id: str) -> str:
    nums = []
    prefix = f"{parent_id}."
    for row in rows:
        if not row.feature_id.startswith(prefix):
            continue
        rest = row.feature_id[len(prefix) :]
        if "." in rest:
            continue
        if rest.isdigit():
            nums.append(int(rest))
    nxt = max(nums, default=0) + 1
    return f"{parent_id}.{nxt:02d}"
