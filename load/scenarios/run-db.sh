#!/usr/bin/env bash
#
# Runs the db rate ladder against whatever variant is currently running on the
# SUT. One cheap query, ~1ms connection hold.
#
# Start a variant on the app server yourself first, then run this here:
#
#   ./run-db.sh              # the whole ladder
#   ./run-db.sh 1000         # one rate
#
# No ssh. The only things it touches are the SUT's HTTP port and k6.

set -uo pipefail
cd "$(dirname "$0")"

SUT="${SUT:-172.31.15.61}"
RATES="${1:-400 800 1000 1200 1600 2400}"
REPS="${REPS:-3}"
DURATION="${DURATION:-60s}"
WARMUP="${WARMUP:-60s}"
OUTDIR="${OUTDIR:-$HOME/results}"

BASE="http://$SUT:8080"
mkdir -p "$OUTDIR"

command -v k6 >/dev/null || { echo "k6 not on PATH"; exit 1; }
# Used to detect dropped iterations. Without it, a cell that failed to sustain
# the offered rate would be recorded as though it were valid.
command -v python3 >/dev/null || { echo "python3 not on PATH (apt install -y python3)"; exit 1; }

# Ask the app which variant it is rather than being told. Every metric carries a
# variant tag, so a result cannot be mislabelled by having started the wrong jar.
VARIANT=$(curl -s --max-time 5 "$BASE/actuator/prometheus" | grep -m1 -o 'variant="[^"]*"' | cut -d'"' -f2)
if [ -z "$VARIANT" ]; then
    echo "nothing answering at $BASE - start a variant on the app server first"
    exit 1
fi

echo "variant:  $VARIANT"
echo "workload: db"
echo "rates:    $RATES   x $REPS reps"
echo

for rate in $RATES; do
    for rep in $(seq 1 "$REPS"); do
        tag="${VARIANT}__db__${rate}rps__r${rep}"
        echo "--- $tag"

        curl -s "$BASE/actuator/prometheus" > "$OUTDIR/$tag.metrics.before.txt"

        BASE_URL="$BASE" RATE="$rate" DURATION="$DURATION" WARMUP="$WARMUP" OUT="$OUTDIR/$tag.json" k6 run --quiet --no-color db.js 2>&1 | grep -vE 'level=(warning|error)' | sed 's/^/    /'

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
