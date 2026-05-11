#!/usr/bin/env bash
# Build a runnable jaffle_shop working dir with scenario 02 (type mismatch)
# applied, then deterministically reproduce the failure against DuckDB and
# capture target/manifest.json + target/run_results.json.
#
# Usage: ./setup.sh [output_dir]
#   default output_dir: $TMPDIR/ambesa-fixture-02-type-mismatch
#
# Mirrors scenarios/01-schema-drift/setup.sh; only the overlay differs.
set -euo pipefail

SCENARIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_ROOT="$(cd "${SCENARIO_DIR}/../.." && pwd)"
REPO_ROOT="$(cd "${FIXTURE_ROOT}/../../.." && pwd)"
BASELINE_DIR="${FIXTURE_ROOT}/baseline"
PROFILES_FILE="${FIXTURE_ROOT}/profiles.yml"
OUT_DIR="${1:-${TMPDIR:-/tmp}/ambesa-fixture-02-type-mismatch}"

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

# dbt seed first — the broken VARCHAR amount loads fine (DuckDB infers type
# from the seed). The breakage shows up at run time when stg_payments tries
# to divide a VARCHAR by 100.
uv run --project "${REPO_ROOT}" dbt seed \
  --project-dir "${OUT_DIR}" \
  --profiles-dir "${OUT_DIR}" \
  --profile jaffle_shop \
  --target dev \
  --no-version-check \
  >/dev/null

# dbt run SHOULD fail at stg_payments — that's the fixture.
uv run --project "${REPO_ROOT}" dbt run \
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
