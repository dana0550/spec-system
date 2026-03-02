from __future__ import annotations

from specctl.command_utils import has_errors, print_messages, project_root
from specctl.validators.project import lint_project


def run(args) -> int:
    root = project_root(args.root)
    messages, _ = lint_project(root)
    print_messages(messages)
    return 1 if has_errors(messages, strict=args.strict) else 0
