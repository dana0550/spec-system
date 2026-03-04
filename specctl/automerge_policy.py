from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence

SUCCESSFUL_CHECK_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}


@dataclass(frozen=True)
class CheckContext:
    name: str
    kind: str
    status: str
    conclusion: str | None = None
    app_slug: str | None = None
    app_name: str | None = None

    @property
    def normalized_name(self) -> str:
        app = " ".join(part for part in [self.app_slug, self.app_name] if part)
        return f"{self.name} {app}".strip().lower()


@dataclass(frozen=True)
class AutoMergeDecision:
    should_merge: bool
    reasons: tuple[str, ...]
    disabled_reason: str | None = None


def parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def is_checkbox_checked(body: str, label: str) -> bool:
    pattern = re.compile(rf"(?mi)^[ \t]*-[ \t]*\[(x|X)\][ \t]*{re.escape(label)}[ \t]*$")
    return bool(pattern.search(body or ""))


def evaluate_auto_merge(
    *,
    state: str,
    merged: bool,
    is_draft: bool,
    mergeable: str | None,
    body: str,
    labels: Iterable[str],
    checks: Sequence[CheckContext],
    unresolved_bugbot_threads: int,
    disable_label: str,
    disable_checkbox_label: str,
    ignored_check_prefixes: Sequence[str],
    bugbot_check_keywords: Sequence[str],
    require_bugbot_check: bool = True,
) -> AutoMergeDecision:
    reasons: list[str] = []
    normalized_labels = {label.lower() for label in labels}
    normalized_disable_label = disable_label.lower().strip()
    ignored_prefixes = tuple(prefix.lower() for prefix in ignored_check_prefixes if prefix)
    bugbot_keywords = tuple(keyword.lower() for keyword in bugbot_check_keywords if keyword)

    if merged or state != "OPEN":
        return AutoMergeDecision(should_merge=False, reasons=("Pull request is not open.",))

    if normalized_disable_label and normalized_disable_label in normalized_labels:
        return AutoMergeDecision(
            should_merge=False,
            reasons=("Auto-merge was disabled with a label override.",),
            disabled_reason=f"Label `{disable_label}` is present.",
        )

    if is_checkbox_checked(body, disable_checkbox_label):
        return AutoMergeDecision(
            should_merge=False,
            reasons=("Auto-merge was disabled in the pull request description.",),
            disabled_reason=f"Checkbox `{disable_checkbox_label}` is checked.",
        )

    if is_draft:
        reasons.append("Pull request is still a draft.")

    if mergeable == "CONFLICTING":
        reasons.append("Pull request has merge conflicts.")
    elif mergeable != "MERGEABLE":
        reasons.append("Mergeability is not ready yet.")

    if unresolved_bugbot_threads > 0:
        reasons.append(f"Bugbot has {unresolved_bugbot_threads} unresolved review thread(s).")

    actionable_checks = [
        check
        for check in checks
        if not any(check.name.lower().startswith(prefix) for prefix in ignored_prefixes)
    ]

    if not actionable_checks:
        reasons.append("No completed checks were found on the pull request head commit.")

    bugbot_checks = [
        check
        for check in actionable_checks
        if bugbot_keywords and any(keyword in check.normalized_name for keyword in bugbot_keywords)
    ]

    if require_bugbot_check and not bugbot_checks:
        reasons.append("Waiting for a bugbot check run to appear.")

    for check in actionable_checks:
        if check.kind == "check_run":
            if check.status != "COMPLETED":
                reasons.append(f"Check `{check.name}` is still {check.status.lower()}.")
                continue
            if check.conclusion not in SUCCESSFUL_CHECK_CONCLUSIONS:
                conclusion = (check.conclusion or "UNKNOWN").lower()
                reasons.append(f"Check `{check.name}` concluded with {conclusion}.")
                continue
        elif check.kind == "status_context":
            if check.status == "SUCCESS":
                continue
            if check.status == "PENDING":
                reasons.append(f"Status `{check.name}` is still pending.")
                continue
            reasons.append(f"Status `{check.name}` is {check.status.lower()}.")
        else:
            reasons.append(f"Unknown check context type `{check.kind}` for `{check.name}`.")

    if reasons:
        return AutoMergeDecision(should_merge=False, reasons=tuple(_dedupe(reasons)))
    return AutoMergeDecision(should_merge=True, reasons=())


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
