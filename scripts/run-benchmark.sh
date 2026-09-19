#!/usr/bin/env bash
#
# Runs the benchmark on EC2 from your laptop.
#
# For each cell it: starts a variant on the SUT, waits for health, snapshots
# metrics, runs k6 on the load generator, snapshots metrics again, stops the
# variant, and copies both halves back into results/raw/.
#
#   scripts/run-benchmark.sh api 500
#   scripts/run-benchmark.sh api                 # whole ladder for that workload
#   scripts/run-benchmark.sh all                 # everything
#
# Configure by editing the block below, or via environment variables.

set -uo pipefail

# ---------------------------------------------------------------------------
# CONFIG - edit these
# ---------------------------------------------------------------------------
KEY="${KEY:-$HOME/.ssh/bench.pem}"        # ssh private key
SUT_HOST="${SUT_HOST:-ubuntu@1.2.3.4}"    # public address, for ssh
LOADGEN_HOST="${LOADGEN_HOST:-ubuntu@5.6.7.8}"
SUT_PRIVATE_IP="${SUT_PRIVATE_IP:-10.0.0.11}"      # what k6 connects to
BACKEND_PRIVATE_IP="${BACKEND_PRIVATE_IP:-10.0.0.12}"  # postgres + stub

REPS="${REPS:-3}"                # repetitions per cell
DURATION="${DURATION:-60s}"      # measured window
WARMUP="${WARMUP:-60s}"          # discarded window; 60s minimum, see docs
POOL_SIZE="${POOL_SIZE:-20}"
JVM_FLAGS="${JVM_FLAGS:--Xms1g -Xmx1g -XX:+UseG1GC}"

VARIANTS="${VARIANTS:-mvc-platform mvc-virtual webflux-r2dbc mvc-jpa}"

# Rate ladders, derived in docs/WORKLOADS.md from the measured knees.
RATES_nodb="1000 2000 4000 8000"
RATES_db="400 800 1000 1200 1600 2400"
RATES_db_heavy="400 800 1000 1200 1600 2400"
RATES_db_slow="50 100 150 200 300 400"
RATES_api="250 500 1000 1500 2000"

# ---------------------------------------------------------------------------

OUT_DIR="results/raw"
SSH="ssh -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"
SCP="scp -i $KEY -o StrictHostKeyChecking=no"

usage() {
    echo "usage: $0 <workload|all> [rate]"
    echo "  workloads: nodb db db-heavy db-slow api"
    exit 1
}

# Look up the rate ladder for a workload (dashes aren't legal in var names).
rates_for() {
    local key
    key="RATES_${1//-/_}"
    echo "${!key:-}"
}

# webflux uses R2DBC, everything else uses JDBC. Same host, different scheme.
db_url_for() {
    if [ "$1" = "webflux-r2dbc" ]; then
        echo "r2dbc:postgresql://$BACKEND_PRIVATE_IP:5432/bench"
    else
        echo "jdbc:postgresql://$BACKEND_PRIVATE_IP:5432/bench"
    fi
}

# --- preflight -------------------------------------------------------------

preflight() {
    echo "checking connectivity..."
    [ -f "$KEY" ] || { echo "ERROR: ssh key not found at $KEY"; exit 1; }

    $SSH "$SUT_HOST" 'ls ~/bench/*.jar >/dev/null 2>&1' \
        || { echo "ERROR: no jars in ~/bench on the SUT"; exit 1; }

    $SSH "$LOADGEN_HOST" 'command -v k6 >/dev/null && ls ~/load/scenarios >/dev/null' \
        || { echo "ERROR: k6 or ~/load/scenarios missing on the load generator"; exit 1; }

    # The stub must answer or every /api cell silently measures connection
    # refusals instead of the application.
    $SSH "$SUT_HOST" "curl -sf http://$BACKEND_PRIVATE_IP:9099/actuator/health >/dev/null" \
        || { echo "ERROR: stub-service not reachable from the SUT"; exit 1; }

    echo "  ok"
    mkdir -p "$OUT_DIR"
}

# --- one cell --------------------------------------------------------------

run_cell() {
    local variant=$1 workload=$2 rate=$3 rep=$4
    local tag="${variant}__${workload}__${rate}rps__r${rep}"
    local db_url; db_url=$(db_url_for "$variant")

    echo "--- $tag"

    # 1. start the variant
    $SSH "$SUT_HOST" "cd ~/bench && \
        DB_URL='$db_url' DB_USER=bench DB_PASSWORD=bench \
        UPSTREAM_URL='http://$BACKEND_PRIVATE_IP:9099' \
        POOL_SIZE=$POOL_SIZE \
        nohup java $JVM_FLAGS -jar $variant-0.0.1-SNAPSHOT.jar > app.log 2>&1 &" \
        >/dev/null 2>&1

    # 2. wait for health
    local up=0
    for _ in $(seq 1 60); do
        if $SSH "$SUT_HOST" 'curl -sf http://localhost:8080/actuator/health >/dev/null'; then
            up=1; break
        fi
        sleep 2
    done
    if [ "$up" -eq 0 ]; then
        echo "    FAILED to start - last log lines:"
        $SSH "$SUT_HOST" 'tail -15 ~/bench/app.log' | sed 's/^/      /'
        stop_variant
        return 1
    fi

    # 3. metrics before
    $SSH "$SUT_HOST" 'curl -s http://localhost:8080/actuator/prometheus' \
        > "$OUT_DIR/$tag.metrics.before.txt"

    # 4. load
    $SSH "$LOADGEN_HOST" "cd ~/load && \
        BASE_URL=http://$SUT_PRIVATE_IP:8080 RATE=$rate \
        DURATION=$DURATION WARMUP=$WARMUP OUT=$tag.json \
        k6 run --quiet --no-color scenarios/$workload.js" 2>&1 \
        | grep -vE 'level=(warning|error)' | sed 's/^/    /'

    # 5. metrics after - must happen before the JVM is stopped
    $SSH "$SUT_HOST" 'curl -s http://localhost:8080/actuator/prometheus' \
        > "$OUT_DIR/$tag.metrics.after.txt"

    # 6. stop, then collect
    stop_variant
    $SCP "$LOADGEN_HOST:~/load/$tag.json" "$OUT_DIR/" >/dev/null 2>&1 \
        || echo "    WARNING: could not fetch $tag.json"

    # 7. flag cells where k6 could not sustain the offered rate
    if [ -f "$OUT_DIR/$tag.json" ]; then
        local dropped
        dropped=$(python -c "
import json,sys
m=json.load(open(sys.argv[1]))['metrics']
print(int(m.get('dropped_iterations{scenario:measure}',{}).get('values',{}).get('count',0)))
" "$OUT_DIR/$tag.json" 2>/dev/null || echo 0)
        if [ "${dropped:-0}" -gt 0 ]; then
            echo "    INVALID: $dropped iterations dropped during measurement"
            touch "$OUT_DIR/$tag.INVALID"
        fi
    fi
    sleep 5   # let sockets drain before the next JVM binds 8080
}

stop_variant() {
    $SSH "$SUT_HOST" 'pkill -f "SNAPSHOT.jar" || true' >/dev/null 2>&1
}

# --- main ------------------------------------------------------------------

[ $# -ge 1 ] || usage
WORKLOAD=$1
SINGLE_RATE=${2:-}

preflight

# Build the cell list, then shuffle it. Randomised order means drift over a long
# run - thermal, a noisy neighbour, a background job - cannot correlate with one
# variant and masquerade as a result.
CELLS=()
if [ "$WORKLOAD" = "all" ]; then
    WORKLOADS="nodb db db-heavy db-slow api"
else
    WORKLOADS="$WORKLOAD"
fi

for wl in $WORKLOADS; do
    if [ -n "$SINGLE_RATE" ]; then
        rates="$SINGLE_RATE"
    else
        rates=$(rates_for "$wl")
        [ -n "$rates" ] || { echo "unknown workload: $wl"; usage; }
    fi
    for variant in $VARIANTS; do
        for rate in $rates; do
            for rep in $(seq 1 "$REPS"); do
                CELLS+=("$variant $wl $rate $rep")
            done
        done
    done
done

mapfile -t CELLS < <(printf '%s\n' "${CELLS[@]}" | shuf)

echo
echo "${#CELLS[@]} cells - roughly $(( ${#CELLS[@]} * 3 / 2 )) minutes"
echo
START=$(date +%s)
i=0
for cell in "${CELLS[@]}"; do
    i=$((i + 1))
    echo "[$i/${#CELLS[@]}]"
    run_cell $cell || echo "    cell failed, continuing"
done

echo
echo "done in $(( ($(date +%s) - START) / 60 )) min"
echo "results in $OUT_DIR/  -  summarise with: python scripts/summarize.py"
