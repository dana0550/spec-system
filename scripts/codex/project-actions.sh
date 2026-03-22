#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
Spec System quick actions
1) specctl check --root .
2) specctl report --root . --json
3) specctl epic check --root . --epic-id E-001
4) specctl oneshot report --root . --epic-id E-001 --json
EOF
