from __future__ import annotations

import re
from pathlib import Path

from specctl.constants import CONTRACT_CHANGE_STATUSES, CONTRACT_CHANGE_TYPES, CONTRACT_TARGET_STATES
from specctl.io_utils import parse_frontmatter, split_markdown_table_row
from specctl.models import ContractChangeRow, ContractChangeStats, LintMessage
from specctl.validators.ids import CONTRACT_CHANGE_ID_RE


REQUIRED_SECTIONS = (
    "Summary",
    "Contract Surface",
    "Change Details",
    "Compatibility and Migration Guidance",
    "Downstream Notification Context",
)
REQUIRED_TARGET_COLUMNS = ("repo", "owner", "context", "pr_url", "state")


def validate_contract_change_rows(rows: list[ContractChangeRow], index_path: Path) -> list[LintMessage]:
    messages: list[LintMessage] = []
    seen: set[str] = set()
    for row in rows:
        cid = row.contract_change_id
        if cid in seen:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_ID_DUPLICATE",
                    message=f"Duplicate contract change ID: {cid}",
                    path=index_path,
                )
            )
        seen.add(cid)

        if not CONTRACT_CHANGE_ID_RE.match(cid):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_ID_FORMAT",
                    message=f"Invalid contract change ID format: {cid}",
                    path=index_path,
                )
            )

        if row.status not in CONTRACT_CHANGE_STATUSES:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_STATUS_INVALID",
                    message=f"Invalid contract change status '{row.status}' for {cid}",
                    path=index_path,
                )
            )

        if row.change_type not in CONTRACT_CHANGE_TYPES:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_TYPE_INVALID",
                    message=f"Invalid contract change type '{row.change_type}' for {cid}",
                    path=index_path,
                )
            )
        if not row.path.startswith("contracts/") or not row.path.endswith(".md"):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_PATH_INVALID",
                    message=f"Contract change path must be under contracts/*.md for {cid}",
                    path=index_path,
                )
            )
    return messages


def validate_contract_change_file(path: Path, row: ContractChangeRow) -> tuple[list[LintMessage], ContractChangeStats]:
    messages: list[LintMessage] = []
    stats = ContractChangeStats()
    stats.contract_changes_total = 1
    if row.status == "draft":
        stats.contract_changes_draft = 1
    elif row.status == "approved":
        stats.contract_changes_approved = 1
    elif row.status == "published":
        stats.contract_changes_published = 1
    elif row.status == "closed":
        stats.contract_changes_closed = 1

    if not path.exists():
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_PATH_MISSING",
                message=f"Contract change path missing: {row.path}",
                path=path,
            )
        )
        return messages, stats

    text = path.read_text(encoding="utf-8")
    frontmatter, _ = parse_frontmatter(text)

    _validate_frontmatter(messages, path, row, frontmatter)
    _validate_sections(messages, path, text)
    header_cols, target_rows, table_messages = _extract_downstream_targets(path, text)
    messages.extend(table_messages)
    if not header_cols:
        return messages, stats

    targets = [target for target in target_rows if any(target.get(col, "") for col in REQUIRED_TARGET_COLUMNS)]
    stats.contract_targets_total += len(targets)
    stats.contract_targets_with_pr_url += sum(1 for target in targets if target.get("pr_url", ""))
    stats.contract_targets_merged += sum(1 for target in targets if target.get("state", "").lower() == "merged")
    messages.extend(_validate_target_gates(path, row.status, targets))
    return messages, stats


def _validate_frontmatter(
    messages: list[LintMessage],
    path: Path,
    row: ContractChangeRow,
    frontmatter: dict,
) -> None:
    required = (
        "doc_type",
        "contract_change_id",
        "name",
        "status",
        "change_type",
        "owner",
        "last_updated",
    )
    for key in required:
        if key not in frontmatter:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_FRONTMATTER_MISSING",
                    message=f"Missing frontmatter key '{key}' in contract change doc",
                    path=path,
                )
            )

    if frontmatter.get("doc_type") != "contract_change":
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_DOC_TYPE_INVALID",
                message="doc_type must be 'contract_change'",
                path=path,
            )
        )

    frontmatter_id = str(frontmatter.get("contract_change_id", ""))
    if frontmatter_id and frontmatter_id != row.contract_change_id:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_ID_MISMATCH",
                message=(
                    f"contract_change_id '{frontmatter_id}' does not match index ID "
                    f"'{row.contract_change_id}'"
                ),
                path=path,
            )
        )

    status = str(frontmatter.get("status", ""))
    if status and status not in CONTRACT_CHANGE_STATUSES:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_STATUS_INVALID",
                message=f"Invalid contract change status '{status}'",
                path=path,
            )
        )
    if status and status in CONTRACT_CHANGE_STATUSES and status != row.status:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_STATUS_MISMATCH",
                message=f"status '{status}' does not match index status '{row.status}'",
                path=path,
            )
        )

    change_type = str(frontmatter.get("change_type", ""))
    if change_type and change_type not in CONTRACT_CHANGE_TYPES:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_TYPE_INVALID",
                message=f"Invalid contract change type '{change_type}'",
                path=path,
            )
        )
    if change_type == "custom":
        custom = str(frontmatter.get("change_type_custom", "")).strip()
        if not custom:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_TYPE_CUSTOM_MISSING",
                    message="change_type_custom is required when change_type=custom",
                    path=path,
                )
            )

    last_updated = str(frontmatter.get("last_updated", ""))
    if last_updated and not re.match(r"^\d{4}-\d{2}-\d{2}$", last_updated):
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_LAST_UPDATED_INVALID",
                message="last_updated must use YYYY-MM-DD format",
                path=path,
            )
        )


def _validate_sections(messages: list[LintMessage], path: Path, text: str) -> None:
    for section in REQUIRED_SECTIONS:
        token = f"## {section}"
        if token not in text:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_SECTION_MISSING",
                    message=f"Missing required section '{token}'",
                    path=path,
                )
            )


def _extract_downstream_targets(
    path: Path,
    text: str,
) -> tuple[list[str], list[dict[str, str]], list[LintMessage]]:
    messages: list[LintMessage] = []
    lines = text.splitlines()
    section_idx = -1
    for idx, line in enumerate(lines):
        if line.strip() == "## Downstream Notification Context":
            section_idx = idx
            break
    if section_idx == -1:
        return [], [], messages

    table_lines: list[tuple[int, str]] = []
    for idx in range(section_idx + 1, len(lines)):
        line = lines[idx]
        if line.startswith("## "):
            break
        if line.strip().startswith("|"):
            table_lines.append((idx + 1, line))

    if len(table_lines) < 2:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_TARGET_TABLE_MISSING",
                message="Downstream Notification Context must include a markdown table header and separator",
                path=path,
            )
        )
        return [], [], messages

    header_line_no, header_line = table_lines[0]
    header = [col.strip().lower() for col in split_markdown_table_row(header_line.strip().strip("|"))]
    missing_cols = [col for col in REQUIRED_TARGET_COLUMNS if col not in header]
    if missing_cols:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_TARGET_COLUMNS_MISSING",
                message=f"Downstream table missing required columns: {', '.join(missing_cols)}",
                path=path,
                line=header_line_no,
            )
        )
        return [], [], messages

    rows: list[dict[str, str]] = []
    for line_no, row_line in table_lines[2:]:
        values = [cell.strip() for cell in split_markdown_table_row(row_line.strip().strip("|"))]
        if not values:
            continue
        padded = values + [""] * (len(header) - len(values))
        row = {header[idx]: padded[idx] if idx < len(padded) else "" for idx in range(len(header))}
        rows.append(row)
        state = row.get("state", "").strip().lower()
        if state and state not in CONTRACT_TARGET_STATES:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_TARGET_STATE_INVALID",
                    message=f"Invalid target state '{row.get('state', '')}'",
                    path=path,
                    line=line_no,
                )
            )
    return header, rows, messages


def _validate_target_gates(path: Path, status: str, targets: list[dict[str, str]]) -> list[LintMessage]:
    messages: list[LintMessage] = []

    if status == "draft":
        return messages

    if not targets:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="CONTRACT_TARGETS_REQUIRED",
                message=f"Status '{status}' requires at least one downstream target row",
                path=path,
            )
        )
        return messages

    has_fully_populated_target = any(
        target.get("repo", "").strip() and target.get("owner", "").strip() and target.get("context", "").strip()
        for target in targets
    )
    if not has_fully_populated_target:
        first_target = targets[0]
        if not first_target.get("repo", "").strip():
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_TARGET_REPO_MISSING",
                    message=f"Status '{status}' requires target repo values",
                    path=path,
                )
            )
        elif not first_target.get("owner", "").strip():
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_TARGET_OWNER_MISSING",
                    message=f"Status '{status}' requires target owner values",
                    path=path,
                )
            )
        else:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="CONTRACT_TARGET_CONTEXT_MISSING",
                    message=f"Status '{status}' requires target context values",
                    path=path,
                )
            )

    if status in {"published", "closed"}:
        required_states = {"opened", "merged"} if status == "published" else {"merged"}
        for target in targets:
            if not target.get("pr_url", "").strip():
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="CONTRACT_TARGET_PR_URL_MISSING",
                        message=f"Status '{status}' requires pr_url for all targets",
                        path=path,
                    )
                )
                break
            state = target.get("state", "").strip().lower()
            if state not in required_states:
                allowed = ", ".join(sorted(required_states))
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="CONTRACT_TARGET_STATE_GATE_FAILED",
                        message=f"Status '{status}' requires target state in [{allowed}]",
                        path=path,
                    )
                )
                break

    return messages
