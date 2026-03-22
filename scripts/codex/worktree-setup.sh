#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f "pyproject.toml" ]]; then
  echo "pyproject.toml not found in $(pwd)"
  exit 1
fi

python -m specctl.cli check --root .
