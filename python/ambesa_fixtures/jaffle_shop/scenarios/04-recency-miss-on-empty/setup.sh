#!/usr/bin/env bash
# Build a runnable jaffle_shop working dir with scenario 03 (null violation)
# applied. Failure surfaces at the dbt TEST phase, not the run phase —
# which means we need to invoke `dbt build` (run + test) rather than just
# `dbt run`. The captured run_results.json then carries the test failure.
#
# Usage: ./setup.sh [output_dir]
#   default output_dir: $TMPDIR/ambesa-fixture-04-recency-miss-on-empty
set -euo pipefail

SCENARIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_ROOT="$(cd "${SCENARIO_DIR}/../.." && pwd)"
REPO_ROOT="$(cd "${FIXTURE_ROOT}/../../.." && pwd)"
BASELINE_DIR="${FIXTURE_ROOT}/baseline"
PROFILES_FILE="${FIXTURE_ROOT}/profiles.yml"
OUT_DIR="${1:-${TMPDIR:-/tmp}/ambesa-fixture-04-recency-miss-on-empty}"

if [[ ! -d "${BASELINE_DIR}" ]]; then
  echo "error: baseline not found at ${BASELINE_DIR}" >&2
  exit 1
fi

rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"
cp -R "${BASELINE_DIR}/." "${OUT_DIR}/"

if [[ -d "${SCENARIO_DIR}/overlay" ]]; then
  cp -R "${SCENARIO_DIR}/overlay/." "${OUT_DIR}/"
fi

cp "${PROFILES_FILE}" "${OUT_DIR}/profiles.yml"

DUCKDB_PATH="${OUT_DIR}/ambesa_fixture.duckdb"
rm -f "${DUCKDB_PATH}"

cd "${REPO_ROOT}"
export PATH="${HOME}/.local/bin:${PATH}"
export DBT_PROFILES_DIR="${OUT_DIR}"
export AMBESA_FIXTURE_DUCKDB_PATH="${DUCKDB_PATH}"

# Use `dbt build` instead of separate seed+run because build chains
# seed → run → test in one invocation, and the failure we want to capture
# is on the TEST node. The captured run_results.json will include both
# successful model runs AND the failed not_null test.
uv run --project "${REPO_ROOT}" dbt build \
  --project-dir "${OUT_DIR}" \
  --profiles-dir "${OUT_DIR}" \
  --profile jaffle_shop \
  --target dev \
  --no-version-check \
  >/dev/null 2>&1 || true

if [[ ! -f "${OUT_DIR}/target/manifest.json" ]]; then
  echo "error: dbt did not produce target/manifest.json — scenario setup broken" >&2
  exit 2
fi
if [[ ! -f "${OUT_DIR}/target/run_results.json" ]]; then
  echo "error: dbt did not produce target/run_results.json — scenario setup broken" >&2
  exit 2
fi

echo "${OUT_DIR}"
