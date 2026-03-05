from __future__ import annotations

import re
from pathlib import Path

from specctl.io_utils import escape_markdown_table_cell, now_date, read_text, split_markdown_table_row, write_text
from specctl.models import EpicRow


TABLE_HEADER = "| ID | Name | Status | Root Feature ID | Epic Path | Owner | Aliases |"
TABLE_RULE = "|----|------|--------|-----------------|-----------|-------|---------|"


def read_epic_rows(path: Path) -> list[EpicRow]:
    if not path.exists():
        return []
    text = read_text(path)
    rows: list[EpicRow] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        if line.strip() in {TABLE_HEADER, TABLE_RULE}:
            continue
        parts = split_markdown_table_row(line.strip().strip("|"))
        if len(parts) < 7:
            continue
        if not parts[0].startswith("E-"):
            continue
        rows.append(
            EpicRow(
                epic_id=parts[0],
                name=parts[1],
                status=parts[2],
                root_feature_id=parts[3],
                epic_path=parts[4],
                owner=parts[5],
                aliases=parts[6],
            )
        )
    return rows


def write_epic_rows(path: Path, rows: list[EpicRow], version: str = "2.1.0") -> None:
    lines = [
        "---",
        "doc_type: epic_index",
        f"version: {version}",
        f"last_synced: {now_date()}",
        "---",
        "# Epics Index",
        "",
        TABLE_HEADER,
        TABLE_RULE,
    ]
    for row in rows:
        lines.append(
            "| "
            f"{escape_markdown_table_cell(row.epic_id)} | "
            f"{escape_markdown_table_cell(row.name)} | "
            f"{escape_markdown_table_cell(row.status)} | "
            f"{escape_markdown_table_cell(row.root_feature_id)} | "
            f"{escape_markdown_table_cell(row.epic_path)} | "
            f"{escape_markdown_table_cell(row.owner)} | "
            f"{escape_markdown_table_cell(row.aliases)} |"
        )
    lines.append("")
    write_text(path, "\n".join(lines))


def next_epic_id(rows: list[EpicRow]) -> str:
    nums = []
    for row in rows:
        match = re.match(r"E-(\d{3})$", row.epic_id)
        if match:
            nums.append(int(match.group(1)))
    nxt = max(nums, default=0) + 1
    return f"E-{nxt:03d}"
