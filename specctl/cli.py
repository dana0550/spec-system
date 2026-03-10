from __future__ import annotations

import argparse

from specctl import __version__
from specctl.commands import (
    approve,
    check,
    epic_check,
    epic_create,
    epic_migrate_agentic,
    feature_check,
    feature_create,
    impact_refresh,
    impact_scan,
    init,
    lint,
    migrate,
    oneshot_check,
    oneshot_finalize,
    oneshot_report,
    oneshot_resume,
    oneshot_run,
    render,
    report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specctl", description="Spec System v2.3 CLI")
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

    feature_check_parser = feature_sub.add_parser("check", help="Check one feature's requirement/traceability integrity")
    feature_check_parser.add_argument("--root", default=".")
    feature_check_parser.add_argument("--feature-id", required=True)
    feature_check_parser.set_defaults(func=feature_check.run)

    impact_parser = subparsers.add_parser("impact", help="Impact analysis operations")
    impact_sub = impact_parser.add_subparsers(dest="impact_command", required=True)

    impact_scan_parser = impact_sub.add_parser("scan", help="Scan for direct and propagated impact suspects")
    impact_scan_parser.add_argument("--root", default=".")
    impact_scan_parser.add_argument("--feature-id")
    impact_scan_parser.add_argument("--json", action="store_true")
    impact_scan_parser.set_defaults(func=impact_scan.run)

    impact_refresh_parser = impact_sub.add_parser("refresh", help="Refresh impact baseline fingerprints")
    impact_refresh_parser.add_argument("--root", default=".")
    impact_refresh_parser.add_argument("--feature-id")
    impact_refresh_parser.add_argument("--ack-upstream", action="store_true")
    impact_refresh_parser.set_defaults(func=impact_refresh.run)

    epic_parser = subparsers.add_parser("epic", help="Epic operations")
    epic_sub = epic_parser.add_subparsers(dest="epic_command", required=True)

    epic_create_parser = epic_sub.add_parser("create", help="Create an epic and scaffold one-shot feature tree")
    epic_create_parser.add_argument("--root", default=".")
    epic_create_parser.add_argument("--name", required=True)
    epic_create_parser.add_argument("--owner", default="unassigned")
    epic_create_parser.add_argument("--brief", required=True)
    epic_create_parser.add_argument("--feature-id")
    epic_create_parser.add_argument("--mode", choices=["agentic", "deterministic"], default="agentic")
    epic_create_parser.add_argument("--runner", choices=["codex", "claude"], default="codex")
    epic_create_parser.add_argument("--interactive", action="store_true")
    epic_create_parser.add_argument("--no-interactive", action="store_true")
    epic_create_parser.add_argument("--answers-file")
    epic_create_parser.add_argument("--question-pack-out")
    epic_create_parser.add_argument(
        "--approval-mode",
        choices=["two-gate", "per-feature", "none"],
        default="two-gate",
    )
    epic_create_parser.add_argument("--research-depth", choices=["deep", "balanced", "lean"], default="deep")
    epic_create_parser.set_defaults(func=epic_create.run)

    epic_check_parser = epic_sub.add_parser("check", help="Validate one epic and its one-shot artifacts")
    epic_check_parser.add_argument("--root", default=".")
    epic_check_parser.add_argument("--epic-id", required=True)
    epic_check_parser.set_defaults(func=epic_check.run)

    epic_migrate_parser = epic_sub.add_parser(
        "migrate-agentic",
        help="Upgrade existing epic feature artifacts to agentic quality baseline",
    )
    epic_migrate_parser.add_argument("--root", default=".")
    epic_migrate_parser.add_argument("--epic-id")
    epic_migrate_parser.add_argument("--runner", choices=["codex", "claude"], default="codex")
    epic_migrate_parser.add_argument("--interactive", action="store_true")
    epic_migrate_parser.add_argument("--no-interactive", action="store_true")
    epic_migrate_parser.add_argument("--answers-file")
    epic_migrate_parser.add_argument("--question-pack-out")
    epic_migrate_parser.add_argument("--check", action="store_true")
    epic_migrate_parser.add_argument("--apply", action="store_true")
    epic_migrate_parser.set_defaults(func=epic_migrate_agentic.run)

    oneshot_parser = subparsers.add_parser("oneshot", help="One-shot epic execution commands")
    oneshot_sub = oneshot_parser.add_subparsers(dest="oneshot_command", required=True)

    oneshot_run_parser = oneshot_sub.add_parser("run", help="Start one-shot execution for an epic")
    oneshot_run_parser.add_argument("--root", default=".")
    oneshot_run_parser.add_argument("--epic-id", required=True)
    oneshot_run_parser.add_argument("--runner", choices=["codex", "claude"])
    oneshot_run_parser.set_defaults(func=oneshot_run.run)

    oneshot_resume_parser = oneshot_sub.add_parser("resume", help="Resume an existing one-shot run")
    oneshot_resume_parser.add_argument("--root", default=".")
    oneshot_resume_parser.add_argument("--epic-id", required=True)
    oneshot_resume_parser.add_argument("--run-id", required=True)
    oneshot_resume_parser.set_defaults(func=oneshot_resume.run)

    oneshot_check_parser = oneshot_sub.add_parser("check", help="Validate one-shot contract and run artifacts")
    oneshot_check_parser.add_argument("--root", default=".")
    oneshot_check_parser.add_argument("--epic-id", required=True)
    oneshot_check_parser.add_argument("--run-id")
    oneshot_check_parser.set_defaults(func=oneshot_check.run)

    oneshot_finalize_parser = oneshot_sub.add_parser("finalize", help="Finalize one-shot run and mark scope done")
    oneshot_finalize_parser.add_argument("--root", default=".")
    oneshot_finalize_parser.add_argument("--epic-id", required=True)
    oneshot_finalize_parser.add_argument("--run-id", required=True)
    oneshot_finalize_parser.set_defaults(func=oneshot_finalize.run)

    oneshot_report_parser = oneshot_sub.add_parser("report", help="Report one-shot metrics for an epic")
    oneshot_report_parser.add_argument("--root", default=".")
    oneshot_report_parser.add_argument("--epic-id", required=True)
    oneshot_report_parser.add_argument("--json", action="store_true")
    oneshot_report_parser.set_defaults(func=oneshot_report.run)

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
