from __future__ import annotations

from argparse import Namespace

from specctl.command_utils import has_errors, print_messages, project_root
from specctl.commands import render
from specctl.validators.project import lint_project


def run(args) -> int:
    root = project_root(args.root)
    messages, stats, _ = lint_project(root)
    print_messages(messages)
    lint_failed = has_errors(messages, strict=args.strict)
    render_rc = render.run(Namespace(root=str(root), check=True, stats=stats))
    return 1 if lint_failed or render_rc != 0 else 0
