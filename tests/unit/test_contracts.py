from __future__ import annotations

from pathlib import Path

from specctl.cli import main
from specctl.contract_index import next_contract_change_id, read_contract_change_rows, write_contract_change_rows
from specctl.models import ContractChangeRow
from specctl.validators.contracts import validate_contract_change_file
from specctl.validators.project import lint_project_with_impact


def test_contract_index_roundtrip_and_next_id(tmp_path: Path) -> None:
    index_path = tmp_path / "CONTRACT_CHANGES.md"
    rows = [
        ContractChangeRow(
            contract_change_id="CC-001",
            name="Auth|Gateway Contract",
            status="draft",
            change_type="api_contract_changed",
            owner="owner@example.com",
            path="contracts/CC-001-auth-gateway-contract.md",
            aliases="[]",
        )
    ]
    write_contract_change_rows(index_path, rows)
    loaded = read_contract_change_rows(index_path)
    assert loaded[0].name == "Auth|Gateway Contract"
    assert next_contract_change_id(loaded) == "CC-002"


def test_contract_validator_requires_custom_type_payload(tmp_path: Path) -> None:
    path = tmp_path / "CC-001-contract.md"
    row = ContractChangeRow(
        contract_change_id="CC-001",
        name="CustomTypeContract",
        status="draft",
        change_type="custom",
        owner="owner@example.com",
        path="contracts/CC-001-contract.md",
        aliases="[]",
    )
    path.write_text(
        "\n".join(
            [
                "---",
                "doc_type: contract_change",
                "contract_change_id: CC-001",
                "name: CustomTypeContract",
                "status: draft",
                "change_type: custom",
                "owner: owner@example.com",
                "last_updated: 2026-03-29",
                "---",
                "# CustomTypeContract",
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
        encoding="utf-8",
    )
    messages, _ = validate_contract_change_file(path, row)
    assert any(message.code == "CONTRACT_TYPE_CUSTOM_MISSING" for message in messages)


def test_contract_validator_published_requires_pr_urls(tmp_path: Path) -> None:
    path = tmp_path / "CC-001-contract.md"
    row = ContractChangeRow(
        contract_change_id="CC-001",
        name="PublishedContract",
        status="published",
        change_type="api_contract_added",
        owner="owner@example.com",
        path="contracts/CC-001-contract.md",
        aliases="[]",
    )
    path.write_text(
        "\n".join(
            [
                "---",
                "doc_type: contract_change",
                "contract_change_id: CC-001",
                "name: PublishedContract",
                "status: published",
                "change_type: api_contract_added",
                "owner: owner@example.com",
                "last_updated: 2026-03-29",
                "---",
                "# PublishedContract",
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
                "| org/repo | owner | consume endpoint |  | opened |",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    messages, _ = validate_contract_change_file(path, row)
    assert any(message.code == "CONTRACT_TARGET_PR_URL_MISSING" for message in messages)


def test_contract_validator_approved_requires_only_one_fully_populated_target(tmp_path: Path) -> None:
    path = tmp_path / "CC-001-contract.md"
    row = ContractChangeRow(
        contract_change_id="CC-001",
        name="ApprovedContract",
        status="approved",
        change_type="api_contract_changed",
        owner="owner@example.com",
        path="contracts/CC-001-contract.md",
        aliases="[]",
    )
    path.write_text(
        "\n".join(
            [
                "---",
                "doc_type: contract_change",
                "contract_change_id: CC-001",
                "name: ApprovedContract",
                "status: approved",
                "change_type: api_contract_changed",
                "owner: owner@example.com",
                "last_updated: 2026-03-29",
                "---",
                "# ApprovedContract",
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
                "| org/repo-1 | owner | consume endpoint |  |  |",
                "|  | owner-2 | second target context |  |  |",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    messages, _ = validate_contract_change_file(path, row)
    assert not any(
        message.code
        in {"CONTRACT_TARGET_REPO_MISSING", "CONTRACT_TARGET_OWNER_MISSING", "CONTRACT_TARGET_CONTEXT_MISSING"}
        for message in messages
    )


def test_contract_validator_reports_status_mismatch_with_index(tmp_path: Path) -> None:
    path = tmp_path / "CC-001-contract.md"
    row = ContractChangeRow(
        contract_change_id="CC-001",
        name="StatusMismatchContract",
        status="draft",
        change_type="api_contract_added",
        owner="owner@example.com",
        path="contracts/CC-001-contract.md",
        aliases="[]",
    )
    path.write_text(
        "\n".join(
            [
                "---",
                "doc_type: contract_change",
                "contract_change_id: CC-001",
                "name: StatusMismatchContract",
                "status: published",
                "change_type: api_contract_added",
                "owner: owner@example.com",
                "last_updated: 2026-03-29",
                "---",
                "# StatusMismatchContract",
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
        encoding="utf-8",
    )
    messages, _ = validate_contract_change_file(path, row)
    assert any(message.code == "CONTRACT_STATUS_MISMATCH" for message in messages)


def test_lint_project_collects_contract_change_stats(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert (
        main(
            [
                "contract",
                "create",
                "--root",
                str(root),
                "--name",
                "StatsContract",
                "--owner",
                "owner@example.com",
                "--change-type",
                "api_contract_changed",
            ]
        )
        == 0
    )
    contract_path = next((root / "docs" / "contracts").glob("CC-001-*.md"))
    contract_path.write_text(
        contract_path.read_text(encoding="utf-8")
        .replace(
            "|------|-------|---------|--------|-------|",
            "|------|-------|---------|--------|-------|\n| org/repo | owner | update parser | https://example.com/pr/1 | merged |",
        )
        .replace("status: draft", "status: closed"),
        encoding="utf-8",
    )
    index_path = root / "docs" / "CONTRACT_CHANGES.md"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace("| draft |", "| closed |"),
        encoding="utf-8",
    )

    _, _, _, _, contract_stats = lint_project_with_impact(root)
    assert contract_stats.contract_changes_total == 1
    assert contract_stats.contract_changes_closed == 1
    assert contract_stats.contract_targets_total == 1
    assert contract_stats.contract_targets_with_pr_url == 1
    assert contract_stats.contract_targets_merged == 1
