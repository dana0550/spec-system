from __future__ import annotations

from pathlib import Path

from specctl.constants import CONTRACT_CHANGE_TYPES
from specctl.contract_index import (
    next_contract_change_id,
    read_contract_change_rows,
    write_contract_change_rows,
)
from specctl.io_utils import now_date, slugify, write_text
from specctl.models import ContractChangeRow
from specctl.validators.ids import CONTRACT_CHANGE_ID_RE


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"
    contracts_dir = docs / "contracts"
    contracts_index_path = docs / "CONTRACT_CHANGES.md"
    rows = read_contract_change_rows(contracts_index_path)

    requested_id = getattr(args, "contract_change_id", None)
    existing_ids = {row.contract_change_id for row in rows}
    if requested_id:
        if not CONTRACT_CHANGE_ID_RE.match(requested_id):
            print(f"[ERROR] Invalid contract change ID format: {requested_id}")
            return 1
        if requested_id in existing_ids:
            print(f"[ERROR] Contract change ID already exists: {requested_id}")
            return 1
        contract_change_id = requested_id
    else:
        contract_change_id = next_contract_change_id(rows)

    change_type = (args.change_type or "service_added").strip()
    if change_type not in CONTRACT_CHANGE_TYPES:
        allowed = ", ".join(sorted(CONTRACT_CHANGE_TYPES))
        print(f"[ERROR] Invalid change type '{change_type}'. Allowed: {allowed}")
        return 1

    name = args.name.strip()
    slug = f"{contract_change_id}-{slugify(name)}"
    path = f"contracts/{slug}.md"
    owner = args.owner or "unassigned"
    row = ContractChangeRow(
        contract_change_id=contract_change_id,
        name=name,
        status="draft",
        change_type=change_type,
        owner=owner,
        path=path,
        aliases="[]",
    )
    rows.append(row)
    rows.sort(key=lambda current: current.contract_change_id)
    write_contract_change_rows(contracts_index_path, rows)

    contracts_dir.mkdir(parents=True, exist_ok=True)
    contract_path = docs / path
    _scaffold_contract_change_file(contract_path, row)
    print(f"Created contract change {row.contract_change_id} at {contract_path}")
    return 0


def _scaffold_contract_change_file(path: Path, row: ContractChangeRow) -> None:
    write_text(
        path,
        "\n".join(
            [
                "---",
                "doc_type: contract_change",
                f"contract_change_id: {row.contract_change_id}",
                f"name: {row.name}",
                "status: draft",
                f"change_type: {row.change_type}",
                f"owner: {row.owner}",
                f"last_updated: {now_date()}",
                "---",
                f"# {row.name}",
                "",
                "## Summary",
                "",
                "## Contract Surface",
                "",
                "## Change Details",
                "",
                "## Compatibility and Migration Guidance",
                "",
                "## Downstream Notification Context",
                "| repo | owner | context | pr_url | state |",
                "|------|-------|---------|--------|-------|",
                "",
            ]
        )
        + "\n",
    )
