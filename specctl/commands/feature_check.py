from __future__ import annotations

from pathlib import Path

from specctl.command_utils import format_message, project_root
from specctl.feature_index import read_feature_rows
from specctl.validators.requirements import validate_requirements_file
from specctl.validators.traceability import validate_feature_traceability


def run(args) -> int:
    root = project_root(args.root)
    docs = root / "docs"
    rows = read_feature_rows(docs / "FEATURES.md")
    target = next((row for row in rows if row.feature_id == args.feature_id), None)
    if target is None:
        print(f"[ERROR] Feature ID not found: {args.feature_id}")
        return 1

    requirements_path = docs / target.spec_path
    feature_dir = requirements_path.parent
    messages = []
    messages.extend(validate_requirements_file(requirements_path))
    trace_messages, _ = validate_feature_traceability(feature_dir)
    messages.extend(trace_messages)

    for message in messages:
        print(format_message(message))
    return 1 if any(message.severity == "ERROR" for message in messages) else 0
