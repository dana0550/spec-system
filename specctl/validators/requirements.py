from __future__ import annotations

import re
from pathlib import Path

from specctl.constants import EARS_TRIGGERS, RFC_KEYWORDS
from specctl.models import LintMessage
from specctl.validators.ids import REQ_ID_RE, SCENARIO_ID_RE


REQ_LINE_RE = re.compile(r"^\s*[-*]\s*(R-F\d{3}(?:\.\d{2})*-\d{3})\s*:\s*(.+)$")
SCENARIO_LINE_RE = re.compile(r"^\s*[-*]\s*(S-F\d{3}(?:\.\d{2})*-\d{3})\s*:\s*(.+)$")


def extract_requirement_ids(text: str) -> list[str]:
    return REQ_ID_RE.findall(text)


def extract_scenario_ids(text: str) -> list[str]:
    return SCENARIO_ID_RE.findall(text)


def validate_requirements_file(path: Path) -> list[LintMessage]:
    messages: list[LintMessage] = []
    if not path.exists():
        return [
            LintMessage(
                severity="ERROR",
                code="REQ_MISSING",
                message="requirements.md is missing",
                path=path,
            )
        ]

    lines = path.read_text(encoding="utf-8").splitlines()
    requirement_count = 0
    scenario_count = 0

    for idx, line in enumerate(lines, start=1):
        req_match = REQ_LINE_RE.match(line)
        if req_match:
            requirement_count += 1
            req_id, statement = req_match.groups()
            if not any(keyword in statement for keyword in RFC_KEYWORDS):
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="REQ_MODAL",
                        message=f"{req_id} does not contain RFC 2119/8174 modal keyword",
                        path=path,
                        line=idx,
                    )
                )
            upper_statement = statement.upper()
            if not any(trigger in upper_statement for trigger in EARS_TRIGGERS):
                messages.append(
                    LintMessage(
                        severity="ERROR",
                        code="REQ_EARS",
                        message=f"{req_id} does not include an EARS trigger (WHEN/IF/WHILE/WHERE/WHENEVER)",
                        path=path,
                        line=idx,
                    )
                )
            continue

        scenario_match = SCENARIO_LINE_RE.match(line)
        if scenario_match:
            scenario_count += 1

    if requirement_count == 0:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="REQ_NONE",
                message="No requirement lines found. Expected '- R-F...: ...' entries",
                path=path,
            )
        )

    if scenario_count == 0:
        messages.append(
            LintMessage(
                severity="ERROR",
                code="SCENARIO_NONE",
                message="No scenario lines found. Expected '- S-F...: ...' entries",
                path=path,
            )
        )

    return messages
