from __future__ import annotations

from specctl.constants import FEATURE_STATUSES
from specctl.models import FeatureRow, LintMessage


def validate_statuses(rows: list[FeatureRow]) -> list[LintMessage]:
    messages: list[LintMessage] = []
    for row in rows:
        if row.status not in FEATURE_STATUSES:
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="STATUS_INVALID",
                    message=f"Invalid lifecycle status '{row.status}' for {row.feature_id}",
                )
            )
    return messages
