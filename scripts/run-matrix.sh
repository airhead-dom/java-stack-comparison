#!/usr/bin/env bash
# Run the full matrix: variants x workloads x rate ladder x repetitions.
#
#   scripts/run-matrix.sh                      # everything
#   WORKLOADS="api" REPS=3 scripts/run-matrix.sh
#
# Cell order is randomised so that any drift over the run -- thermal, noisy
# neighbour, background process -- does not correlate with a single variant.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

REPS="${REPS:-3}"
read -ra WL <<< "${WORKLOADS:-nodb db db-heavy db-slow api}"
read -ra VS <<< "${VARIANTS_OVERRIDE:-${VARIANTS[*]}}"

preflight

CELLS=()
for variant in "${VS[@]}"; do
  for workload in "${WL[@]}"; do
    for rate in ${LADDER[$workload]}; do
      for rep in $(seq 1 "$REPS"); do
        CELLS+=("$variant $workload $rate $rep")
      done
    done
  done
done

mapfile -t CELLS < <(printf '%s\n' "${CELLS[@]}" | shuf)

echo "${#CELLS[@]} cells queued"
START=$(date +%s)
i=0
for cell in "${CELLS[@]}"; do
  i=$((i + 1))
  echo "[$i/${#CELLS[@]}] $cell"
  # shellcheck disable=SC2086
  "$ROOT/scripts/run-one.sh" $cell || echo "  cell failed, continuing"
  sleep 5   # let the OS reclaim sockets before the next process binds 8080
done
echo "done in $(( ($(date +%s) - START) / 60 )) min -- results in results/raw/"
