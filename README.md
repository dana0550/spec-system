<p align="center">
  <img src="./assets/readme/hero.svg" alt="docs-spec-system hero" width="100%" />
</p>

<h1 align="center">docs-spec-system</h1>

<p align="center">
  Contract-first specs for long-horizon AI software delivery.
</p>

<p align="center">
  <a href="https://github.com/dana0550/spec-system/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/dana0550/spec-system/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://github.com/dana0550/spec-system/actions/workflows/release.yml"><img src="https://img.shields.io/github/actions/workflow/status/dana0550/spec-system/release.yml?label=Release" alt="Release"></a>
  <a href="https://github.com/dana0550/spec-system/releases"><img src="https://img.shields.io/github/v/release/dana0550/spec-system" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/specctl-v2.4.0-0E8A92" alt="specctl v2.4.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
</p>

<p align="center">
  <a href="#what-this-is">What This Is</a> •
  <a href="#quickstart">Quickstart</a> •
  <a href="#workflow">Workflow</a> •
  <a href="#epics-and-one-shot">Epics & One-shot</a> •
  <a href="#agent-setup">Agent Setup</a> •
  <a href="#cli-reference">CLI</a>
</p>

## What This Is
`docs-spec-system` gives teams a deterministic spec workflow that scales with AI-assisted development.

It keeps planning and execution synchronized with strict traceability and gated approvals:

- `R -> D -> T -> S -> evidence`
- EARS + RFC requirement quality checks
- Epic one-shot runtime with blocker policies and finalize gates
- Generated product map and traceability reports

### What ships in this repo
| Module | Purpose |
|---|---|
| `specctl` CLI | Bootstrap, lint/render/check, approvals, migration, epic + one-shot orchestration |
| `skills/docs-spec-system/` | Codex/Claude skill pack with rules, workflows, and templates |
| `.claude-plugin/` | Claude Code plugin packaging |
| `tests/` | Unit + integration tests for lifecycle and runtime integrity |

## Quickstart
### Install
```bash
git clone https://github.com/dana0550/spec-system.git
cd spec-system
python -m pip install -e .
```

### Bootstrap a new specs workspace
```bash
specctl init
specctl feature create --name "User Authentication" --owner team@example.com
specctl render
specctl check
```

### Validate quality gates
```bash
specctl lint --strict
specctl render --check
specctl check --strict
```

## Workflow
### Feature workflow (phase-gated)
1. `requirements_draft -> requirements_approved`
2. `design_draft -> design_approved`
3. `tasks_draft -> tasks_approved`
4. `implementing -> verifying -> done`

Each feature lives in `docs/features/F-###-<slug>/`:

- `requirements.md`
- `design.md`
- `tasks.md`
- `verification.md`

### Core invariants
- Requirements use EARS trigger terms and RFC modal keywords.
- Acceptance scenarios use Gherkin shape (`Given/When/Then`).
- IDs are immutable once assigned.
- Traceability chain is complete before completion.
- Generated docs remain deterministic for identical inputs.

```mermaid
flowchart LR
  A["requirements"] --> B["design"]
  B --> C["tasks"]
  C --> D["verification"]
  D --> E["traceability report"]
```

## Epics and One-shot
Epics are orchestration units with first-class runtime control.

### Epic create
```bash
specctl epic create \
  --name "Billing Reliability" \
  --owner team@example.com \
  --brief ./brief.md \
  --mode agentic
```

Required brief sections:

- `Vision`
- `Outcomes`
- `User Journeys`
- `Constraints`
- `Non-Goals`

### One-shot execution lifecycle
```bash
specctl oneshot run --epic-id E-001 --runner codex
specctl oneshot check --epic-id E-001
specctl oneshot resume --epic-id E-001 --run-id RUN-<timestamp>
specctl oneshot finalize --epic-id E-001 --run-id RUN-<timestamp>
specctl oneshot report --epic-id E-001
```

Finalize is blocked unless all conditions pass:

- zero open blockers
- zero unresolved `ONESHOT-BLOCKER:*` markers
- finalize validation commands pass
- full scoped traceability (`R -> D -> T -> S -> evidence`)

## Agent Setup
### Codex
```bash
specctl codex setup --root .
specctl codex check --root .
```

Optional skill install:
```bash
install-skill-from-github.py --repo dana0550/spec-system --path skills/docs-spec-system
```

References:
- <https://developers.openai.com/codex/app>
- <https://developers.openai.com/codex/cli/reference>
- <https://developers.openai.com/codex/guides/agents-md>

### Claude Code
```text
/plugin marketplace add dana0550/spec-system
/plugin install docs-spec-system@spec-system-plugins
```

Then use `/docs-spec-system:spec-system`.

References:
- <https://docs.anthropic.com/en/docs/claude-code/quickstart>
- <https://docs.anthropic.com/en/docs/claude-code/cli-reference>

## CLI Reference
### Common commands
```bash
specctl init

specctl feature create --name "..." --owner <owner>
specctl feature check --feature-id F-###

specctl impact scan [--feature-id F-###] [--json]
specctl impact refresh [--feature-id F-###] [--ack-upstream]

specctl epic create --name "..." --owner <owner> --brief ./brief.md \
  [--mode agentic|deterministic] \
  [--runner codex|claude]
specctl epic check --epic-id E-###

specctl oneshot run --epic-id E-### [--runner codex|claude]
specctl oneshot resume --epic-id E-### --run-id RUN-...
specctl oneshot check --epic-id E-### [--run-id RUN-...]
specctl oneshot finalize --epic-id E-### --run-id RUN-...
specctl oneshot report --epic-id E-###

specctl lint [--strict]
specctl render [--check]
specctl check [--strict]
specctl approve --feature-id F-### --phase requirements|design|tasks
specctl migrate-v1-to-v2
specctl report
```

Run `specctl --help` for the complete command surface.

## Repository Layout
```text
docs/
  MASTER_SPEC.md
  FEATURES.md
  EPICS.md
  PRODUCT_MAP.md
  TRACEABILITY.md
  STEERING.md
  DECISIONS/
  features/
  epics/
skills/
  docs-spec-system/
specctl/
tests/
```

## Release Model
- Semver tags and GitHub Releases are the public version surface.
- CI enforces lint/render/check and test quality gates.
- Keep generated docs committed and synchronized (`specctl render --check`).

## License
MIT
