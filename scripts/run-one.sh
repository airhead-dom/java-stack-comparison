#!/usr/bin/env bash
# Run a single cell: one variant, one workload, one rate.
#
#   scripts/run-one.sh mvc-platform api 1000 [repetition]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

VARIANT=${1:?variant} WORKLOAD=${2:?workload} RATE=${3:?rate} REP=${4:-1}
DURATION="${DURATION:-60s}" WARMUP="${WARMUP:-30s}"

preflight
OUTDIR="$ROOT/results/raw"
mkdir -p "$OUTDIR"
TAG="${VARIANT}__${WORKLOAD}__${RATE}rps__run${REP}"

echo "=== $TAG ==="
LOG="$OUTDIR/$TAG.app.log"
# One recording per cell, so a pinning or GC question can be answered from the
# exact run that raised it rather than re-run later.
export BENCH_JVM_EXTRA="-XX:StartFlightRecording=settings=profile,dumponexit=true,filename=$OUTDIR/$TAG.jfr"
PID=$(start_variant "$VARIANT" "$LOG")
# shellcheck disable=SC2064
trap "kill $PID 2>/dev/null || true" EXIT

if ! wait_healthy "$SUT_URL"; then
  echo "  FAILED to start; last log lines:"; tail -20 "$LOG"; exit 1
fi

snapshot_metrics "$OUTDIR/$TAG.metrics.before.txt"

BASE_URL="$SUT_URL" RATE="$RATE" DURATION="$DURATION" WARMUP="$WARMUP" \
OUT="$OUTDIR/$TAG.k6.json" \
  "$K6_BIN" run --quiet --no-color "$ROOT/load/scenarios/$WORKLOAD.js" || K6_STATUS=$?

snapshot_metrics "$OUTDIR/$TAG.metrics.after.txt"

kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
trap - EXIT
# A threshold breach on latency or errors is a RESULT -- finding where the SLA
# breaks is the point of the ladder. A dropped iteration during the measured
# phase is different: it means k6 failed to offer the target rate, so the cell
# is not a valid open-model measurement and must not be plotted.
DROPPED=$(python -c "
import json,sys
ms=json.load(open(sys.argv[1]))['metrics']
d=ms.get('dropped_iterations{scenario:measure}',{}).get('values',{})
print(int(d.get('count',0)))
" "$OUTDIR/$TAG.k6.json" 2>/dev/null || echo 0)
if grep -q 'Insufficient VUs' "$LOG" 2>/dev/null || [ "${DROPPED:-0}" -gt 0 ]; then
  echo "  !! INVALID CELL: $DROPPED iterations dropped -- the generator could not"
  echo "     sustain the offered rate. Raise TIMEOUT_MS headroom or load-gen capacity."
  touch "$OUTDIR/$TAG.INVALID"
fi
echo "  written: $OUTDIR/$TAG.*"
exit 0
