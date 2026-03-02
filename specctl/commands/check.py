from __future__ import annotations

from argparse import Namespace

from specctl.commands import lint, render


def run(args) -> int:
    lint_rc = lint.run(args)
    render_rc = render.run(Namespace(root=args.root, check=True))
    return 1 if lint_rc != 0 or render_rc != 0 else 0
