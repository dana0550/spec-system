from __future__ import annotations

import re

from specctl.models import FeatureRow, LintMessage

FEATURE_ID_RE = re.compile(r"^F-\d{3}(?:\.\d{2})*$")
REQ_ID_RE = re.compile(r"R-F\d{3}(?:\.\d{2})*-\d{3}")
SCENARIO_ID_RE = re.compile(r"S-F\d{3}(?:\.\d{2})*-\d{3}")


def validate_feature_ids(rows: list[FeatureRow]) -> list[LintMessage]:
    messages: list[LintMessage] = []
    seen: set[str] = set()
    for row in rows:
        if row.feature_id in seen:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="ID_DUPLICATE",
                    message=f"Duplicate feature ID: {row.feature_id}",
                )
            )
        seen.add(row.feature_id)
        if not FEATURE_ID_RE.match(row.feature_id):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="ID_FORMAT",
                    message=f"Invalid feature ID format: {row.feature_id}",
                )
            )
    return messages
