#!/usr/bin/env bash
# Top-level scenario runner.
# Usage: ./run.sh <scenario-name> [output_dir]
# Example: ./run.sh 01-schema-drift
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO="${1:-}"

if [[ -z "${SCENARIO}" ]]; then
  echo "usage: $0 <scenario-name>" >&2
  echo "available scenarios:" >&2
  ls -1 "${SCRIPT_DIR}/scenarios" 2>/dev/null | sed 's/^/  /' >&2
  exit 2
fi

SCENARIO_DIR="${SCRIPT_DIR}/scenarios/${SCENARIO}"
if [[ ! -d "${SCENARIO_DIR}" ]]; then
  echo "error: unknown scenario ${SCENARIO}" >&2
  exit 2
fi

if [[ ! -x "${SCENARIO_DIR}/setup.sh" ]]; then
  chmod +x "${SCENARIO_DIR}/setup.sh"
fi

OUT_DIR=$("${SCENARIO_DIR}/setup.sh" "${2:-}")
echo "scenario built at: ${OUT_DIR}" >&2
echo "${OUT_DIR}"
