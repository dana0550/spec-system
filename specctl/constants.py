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
    "requirements": {
        "from": ("requirements_draft",),
        "to": "requirements_approved",
    },
    "design": {
        "from": ("requirements_approved", "design_draft"),
        "to": "design_approved",
    },
    "tasks": {
        "from": ("design_approved", "tasks_draft"),
        "to": "tasks_approved",
    },
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

# Exit code used when user input is required to continue an agentic workflow.
NEEDS_INPUT_EXIT_CODE = 2

AGENTIC_QUALITY_MINIMUMS = {
    "requirements": 3,
    "scenarios": 2,
    "design_decisions": 2,
    "tasks": 3,
}

AGENTIC_DESIGN_REQUIRED_SECTIONS = [
    "Architecture",
    "Contracts and Data",
    "UX Behavior",
    "Observability",
    "Risks and Tradeoffs",
    "Requirement Mapping",
]
