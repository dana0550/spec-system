from __future__ import annotations

FEATURE_STATUSES = {
    "requirements_draft",
    "requirements_approved",
    "design_draft",
    "design_approved",
    "tasks_draft",
    "tasks_approved",
    "implementing",
    "verifying",
    "done",
    "deprecated",
}

EPIC_STATUSES = {
    "planning",
    "implementing",
    "verifying",
    "done",
    "blocked",
    "deprecated",
}

APPROVAL_TRANSITIONS = {
    "requirements": ("requirements_draft", "requirements_approved"),
    "design": ("design_draft", "design_approved"),
    "tasks": ("tasks_draft", "tasks_approved"),
}

RFC_KEYWORDS = {
    "MUST",
    "MUST NOT",
    "REQUIRED",
    "SHALL",
    "SHALL NOT",
    "SHOULD",
    "SHOULD NOT",
    "RECOMMENDED",
    "NOT RECOMMENDED",
    "MAY",
    "OPTIONAL",
}

EARS_TRIGGERS = {"WHEN", "IF", "WHILE", "WHERE", "WHENEVER"}

REQUIRED_DOC_FILES = {
    "MASTER_SPEC.md",
    "FEATURES.md",
    "PRODUCT_MAP.md",
    "TRACEABILITY.md",
    "STEERING.md",
}

ONESHOT_PLACEHOLDER_PREFIX = "ONESHOT-BLOCKER:"
