from __future__ import annotations

import re
from pathlib import Path

from specctl.io_utils import escape_markdown_table_cell, now_date, read_text, split_markdown_table_row, write_text
from specctl.models import ContractChangeRow


TABLE_HEADER = "| ID | Name | Status | Change Type | Owner | Path | Aliases |"
TABLE_RULE = "|----|------|--------|-------------|-------|------|---------|"


def read_contract_change_rows(path: Path) -> list[ContractChangeRow]:
    if not path.exists():
        return []
    text = read_text(path)
    rows: list[ContractChangeRow] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        if line.strip() in {TABLE_HEADER, TABLE_RULE}:
            continue
        parts = split_markdown_table_row(line.strip().strip("|"))
        if len(parts) < 7:
            continue
        if not parts[0].startswith("CC-"):
            continue
        rows.append(
            ContractChangeRow(
                contract_change_id=parts[0],
                name=parts[1],
                status=parts[2],
                change_type=parts[3],
                owner=parts[4],
                path=parts[5],
                aliases=parts[6],
            )
        )
    return rows


def write_contract_change_rows(path: Path, rows: list[ContractChangeRow], version: str = "2.1.0") -> None:
    lines = [
        "---",
        "doc_type: contract_change_index",
        f"version: {version}",
        f"last_synced: {now_date()}",
        "---",
        "# Contract Changes Index",
        "",
        TABLE_HEADER,
        TABLE_RULE,
    ]
    for row in rows:
        lines.append(
            "| "
            f"{escape_markdown_table_cell(row.contract_change_id)} | "
            f"{escape_markdown_table_cell(row.name)} | "
            f"{escape_markdown_table_cell(row.status)} | "
            f"{escape_markdown_table_cell(row.change_type)} | "
            f"{escape_markdown_table_cell(row.owner)} | "
            f"{escape_markdown_table_cell(row.path)} | "
            f"{escape_markdown_table_cell(row.aliases)} |"
        )
    lines.append("")
    write_text(path, "\n".join(lines))


def next_contract_change_id(rows: list[ContractChangeRow]) -> str:
    nums = []
    for row in rows:
        match = re.match(r"CC-(\d{3})$", row.contract_change_id)
        if match:
            nums.append(int(match.group(1)))
    nxt = max(nums, default=0) + 1
    return f"CC-{nxt:03d}"
