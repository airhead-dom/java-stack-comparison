#!/usr/bin/env bash

set -uo pipefail
cd "$(dirname "$0")"

SUT="${SUT:-172.31.15.61}"
RATES="${1:-1000 2000 4000 8000}"
REPS="${REPS:-3}"
DURATION="${DURATION:-60s}"
WARMUP="${WARMUP:-60s}"
OUTDIR="${OUTDIR:-$HOME/results}"

BASE="http://$SUT:8080"
mkdir -p "$OUTDIR"

# Ask the app which variant it is rather than being told. Every metric carries a
# variant tag, so a result cannot be mislabelled by having started the wrong jar.
VARIANT=$(curl -s --max-time 5 "$BASE/actuator/prometheus" | grep -m1 -o 'variant="[^"]*"' | cut -d'"' -f2)
if [ -z "$VARIANT" ]; then
    echo "nothing answering at $BASE - start a variant on the app server first"
    exit 1
fi

echo "variant:  $VARIANT"
echo "workload: nodb"
echo "rates:    $RATES   x $REPS reps"
echo

for rate in $RATES; do
    for rep in $(seq 1 "$REPS"); do
        tag="${VARIANT}__nodb__${rate}rps__r${rep}"
        echo "--- $tag"

        curl -s "$BASE/actuator/prometheus" > "$OUTDIR/$tag.metrics.before.txt"

        BASE_URL="$BASE" RATE="$rate" DURATION="$DURATION" WARMUP="$WARMUP" OUT="$OUTDIR/$tag.json" k6 run --quiet --no-color nodb.js 2>&1 | grep -vE 'level=(warning|error)' | sed 's/^/    /'

        # Taken while the JVM is still up. This data is gone once it stops.
        curl -s "$BASE/actuator/prometheus" > "$OUTDIR/$tag.metrics.after.txt"

        # A drop during the measured phase means k6 could not offer the target
        # rate, so the cell is not a valid open-model measurement.
        dropped=$(python3 -c "import json,sys;m=json.load(open(sys.argv[1]))['metrics'];print(int(m.get('dropped_iterations{scenario:measure}',{}).get('values',{}).get('count',0)))" "$OUTDIR/$tag.json" 2>/dev/null || echo 0)
        if [ "${dropped:-0}" -gt 0 ]; then
            echo "    INVALID: $dropped iterations dropped"
            touch "$OUTDIR/$tag.INVALID"
        fi
    done
done

echo
echo "done - results in $OUTDIR"
