from __future__ import annotations

import argparse

from specctl import __version__
from specctl.commands import approve, check, feature_create, init, lint, migrate, render, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specctl", description="Spec System v2 CLI")
    parser.add_argument("--version", action="version", version=f"specctl {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize docs/ v2 skeleton")
    init_parser.add_argument("--root", default=".")
    init_parser.set_defaults(func=init.run)

    feature_parser = subparsers.add_parser("feature", help="Feature operations")
    feature_sub = feature_parser.add_subparsers(dest="feature_command", required=True)

    feature_create_parser = feature_sub.add_parser("create", help="Create a feature with v2 file set")
    feature_create_parser.add_argument("--root", default=".")
    feature_create_parser.add_argument("--name", required=True)
    feature_create_parser.add_argument("--feature-id")
    feature_create_parser.add_argument("--parent-id")
    feature_create_parser.add_argument("--status", default="requirements_draft")
    feature_create_parser.add_argument("--owner", default="unassigned")
    feature_create_parser.set_defaults(func=feature_create.run)

    lint_parser = subparsers.add_parser("lint", help="Lint docs against v2 rules")
    lint_parser.add_argument("--root", default=".")
    lint_parser.add_argument("--strict", action="store_true")
    lint_parser.set_defaults(func=lint.run)

    render_parser = subparsers.add_parser("render", help="Render generated docs")
    render_parser.add_argument("--root", default=".")
    render_parser.add_argument("--check", action="store_true")
    render_parser.set_defaults(func=render.run)

    check_parser = subparsers.add_parser("check", help="Run lint + render --check")
    check_parser.add_argument("--root", default=".")
    check_parser.add_argument("--strict", action="store_true")
    check_parser.set_defaults(func=check.run)

    approve_parser = subparsers.add_parser("approve", help="Advance feature phase approval")
    approve_parser.add_argument("--root", default=".")
    approve_parser.add_argument("--feature-id", required=True)
    approve_parser.add_argument("--phase", required=True, choices=["requirements", "design", "tasks"])
    approve_parser.set_defaults(func=approve.run)

    migrate_parser = subparsers.add_parser("migrate-v1-to-v2", help="Migrate v1 docs layout to v2")
    migrate_parser.add_argument("--root", default=".")
    migrate_parser.set_defaults(func=migrate.run)

    report_parser = subparsers.add_parser("report", help="Output quality/coverage report")
    report_parser.add_argument("--root", default=".")
    report_parser.add_argument("--json", action="store_true")
    report_parser.set_defaults(func=report.run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
