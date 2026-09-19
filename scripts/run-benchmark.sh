#!/usr/bin/env bash
#
# Runs the benchmark on EC2 from your laptop.
#
# For each cell it: starts a variant on the SUT, waits for health, snapshots
# metrics, runs k6 on the load generator, snapshots metrics again, stops the
# variant, and copies both halves back into results/raw/.
#
#   scripts/run-benchmark.sh check               # preflight only, run nothing
#   scripts/run-benchmark.sh api 500
#   scripts/run-benchmark.sh api                 # whole ladder for that workload
#   scripts/run-benchmark.sh all                 # everything
#
# Configure by editing the block below, or via environment variables.

set -uo pipefail

# ---------------------------------------------------------------------------
# CONFIG - edit these
# ---------------------------------------------------------------------------
KEY="${KEY:-$HOME/.ssh/myec.pem}"                        # ssh private key
SUT_HOST="${SUT_HOST:-ubuntu@app-sandbox}"               # public address, for ssh
LOADGEN_HOST="${LOADGEN_HOST:-ubuntu@client-sandbox}"
SUT_PRIVATE_IP="${SUT_PRIVATE_IP:-172.31.15.61}"         # what k6 connects to
BACKEND_PRIVATE_IP="${BACKEND_PRIVATE_IP:-172.31.3.118}" # postgres + stub

# Where things live on the remote boxes. The \$HOME is escaped so it expands
# there, not here.
SUT_DIR="${SUT_DIR:-\$HOME}"                     # the variant jars
LOADGEN_DIR="${LOADGEN_DIR:-\$HOME/scenarios}"   # the k6 .js files

DB_NAME="${DB_NAME:-bench}"
DB_USER="${DB_USER:-bench}"
DB_PASSWORD="${DB_PASSWORD:-bench}"
EXPECTED_ACCOUNTS="${EXPECTED_ACCOUNTS:-200000}"   # rows the seed should have left

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
FAILED=0

usage() {
    echo "usage: $0 <workload|all|check> [rate]"
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
        echo "r2dbc:postgresql://$BACKEND_PRIVATE_IP:5432/$DB_NAME"
    else
        echo "jdbc:postgresql://$BACKEND_PRIVATE_IP:5432/$DB_NAME"
    fi
}

# ---------------------------------------------------------------------------
# PREFLIGHT
#
# Everything a run depends on, checked before a single cell burns time. Each
# check prints its own line, so a failure names the broken link in the chain
# instead of just reporting that something is wrong.
# ---------------------------------------------------------------------------

ok()   { printf '  %-40s OK    %s\n' "$1" "${2:-}"; }
bad()  { printf '  %-40s FAIL  %s\n' "$1" "${2:-}"; FAILED=1; }
warn() { printf '  %-40s WARN  %s\n' "$1" "${2:-}"; }

preflight() {
    echo "preflight"

    # --- laptop ---
    if [ -f "$KEY" ]; then ok "ssh key present"; else
        bad "ssh key present" "$KEY not found"; return
    fi

    # --- SUT reachable ---
    local sut_uname
    sut_uname=$($SSH "$SUT_HOST" 'uname -sm' 2>/dev/null)
    if [ -n "$sut_uname" ]; then ok "ssh to SUT" "$sut_uname"; else
        bad "ssh to SUT" "$SUT_HOST unreachable"; return
    fi

    # --- SUT toolchain and artefacts ---
    local jver
    jver=$($SSH "$SUT_HOST" 'java -version 2>&1 | head -1' 2>/dev/null)
    if [ -n "$jver" ]; then ok "java on SUT" "$jver"; else
        bad "java on SUT" "not installed or not on PATH"
    fi

    for v in $VARIANTS; do
        $SSH "$SUT_HOST" "test -f $SUT_DIR/$v-0.0.1-SNAPSHOT.jar" \
            && ok "jar: $v" \
            || bad "jar: $v" "missing from $SUT_DIR"
    done

    # --- nothing already holding 8080 ---
    if $SSH "$SUT_HOST" 'curl -sf http://localhost:8080/actuator/health >/dev/null 2>&1'; then
        warn "port 8080 free on SUT" "something is running there; it will be killed"
    else
        ok "port 8080 free on SUT"
    fi

    # --- POSTGRES, reached the way the app will reach it ---
    if $SSH "$SUT_HOST" "timeout 5 bash -c '</dev/tcp/$BACKEND_PRIVATE_IP/5432' 2>/dev/null"; then
        ok "postgres port open from SUT" "$BACKEND_PRIVATE_IP:5432"
    else
        bad "postgres port open from SUT" "refused - check the security group allows 5432 within itself"
    fi

    if $SSH "$SUT_HOST" 'command -v psql >/dev/null 2>&1'; then
        local rows
        rows=$($SSH "$SUT_HOST" "PGPASSWORD=$DB_PASSWORD psql -h $BACKEND_PRIVATE_IP \
            -U $DB_USER -d $DB_NAME -tAc 'select count(*) from accounts'" 2>/dev/null | tr -d '\r ')
        if [ -z "${rows:-}" ]; then
            bad "postgres query" "port open but the query failed - credentials or database name?"
        elif [ "$rows" -ge "$EXPECTED_ACCOUNTS" ] 2>/dev/null; then
            ok "postgres seeded" "$rows accounts"
        else
            bad "postgres seeded" "only $rows accounts, expected $EXPECTED_ACCOUNTS - seed incomplete"
        fi
    else
        warn "postgres seeded" "psql not on the SUT, cannot verify row counts"
    fi

    # --- STUB, the backend API ---
    if $SSH "$SUT_HOST" "curl -sf --max-time 5 http://$BACKEND_PRIVATE_IP:9099/actuator/health >/dev/null"; then
        ok "stub health from SUT" "$BACKEND_PRIVATE_IP:9099"
    else
        bad "stub health from SUT" "$BACKEND_PRIVATE_IP:9099 not answering"
    fi

    # Health alone is not enough. The endpoint must return the expected body AND
    # actually delay, or every /api cell measures something other than a 200ms
    # upstream call.
    local body
    body=$($SSH "$SUT_HOST" "curl -s --max-time 5 'http://$BACKEND_PRIVATE_IP:9099/upstream?delayMs=200'" 2>/dev/null)
    if echo "$body" | grep -q 'UPSTREAM-OK'; then
        local elapsed
        elapsed=$($SSH "$SUT_HOST" "curl -s -o /dev/null -w '%{time_total}' --max-time 5 \
            'http://$BACKEND_PRIVATE_IP:9099/upstream?delayMs=200'" 2>/dev/null | tr -d '\r')
        if awk "BEGIN{exit !(${elapsed:-0} > 0.15)}" 2>/dev/null; then
            ok "stub delays correctly" "${elapsed}s for delayMs=200"
        else
            bad "stub delays correctly" "returned in ${elapsed}s, expected ~0.2s"
        fi
    else
        bad "stub /upstream response" "unexpected body: $(echo "$body" | head -c 60)"
    fi

    # --- LOAD GENERATOR ---
    local k6v
    k6v=$($SSH "$LOADGEN_HOST" 'k6 version 2>/dev/null | head -1' 2>/dev/null)
    if [ -n "$k6v" ]; then ok "k6 on load generator" "$k6v"; else
        bad "k6 on load generator" "not installed or not on PATH"
    fi

    local missing=""
    for wl in nodb db db-heavy db-slow api; do
        $SSH "$LOADGEN_HOST" "test -f $LOADGEN_DIR/$wl.js" || missing="$missing $wl.js"
    done
    if [ -z "$missing" ]; then ok "k6 scenarios present" "5 files"; else
        bad "k6 scenarios present" "missing:$missing"
    fi

    # The scenarios import ../lib/common.js; without it every run dies at parse.
    $SSH "$LOADGEN_HOST" "test -f $LOADGEN_DIR/../lib/common.js" \
        && ok "lib/common.js present" \
        || bad "lib/common.js present" "scenarios import ../lib/common.js relative to $LOADGEN_DIR"

    # --- load generator can reach the SUT ---
    if $SSH "$LOADGEN_HOST" "timeout 5 bash -c '</dev/tcp/$SUT_PRIVATE_IP/8080' 2>/dev/null"; then
        ok "load generator reaches SUT:8080"
    else
        warn "load generator reaches SUT:8080" "nothing listening yet - expected when no variant is running"
    fi

    echo
}

# ---------------------------------------------------------------------------
# ONE CELL
# ---------------------------------------------------------------------------

stop_variant() {
    $SSH "$SUT_HOST" 'pkill -f "SNAPSHOT.jar" || true' >/dev/null 2>&1
}

run_cell() {
    local variant=$1 workload=$2 rate=$3 rep=$4
    local tag="${variant}__${workload}__${rate}rps__r${rep}"
    local db_url; db_url=$(db_url_for "$variant")

    echo "--- $tag"

    # Re-check the dependency this workload actually needs. Either can die
    # mid-matrix and leave every later cell silently measuring failures.
    if [ "$workload" = "api" ]; then
        $SSH "$SUT_HOST" "curl -sf --max-time 5 http://$BACKEND_PRIVATE_IP:9099/actuator/health >/dev/null" \
            || { echo "    SKIPPED: stub not answering"; return 1; }
    else
        $SSH "$SUT_HOST" "timeout 5 bash -c '</dev/tcp/$BACKEND_PRIVATE_IP/5432' 2>/dev/null" \
            || { echo "    SKIPPED: postgres not answering"; return 1; }
    fi

    # 1. start the variant
    $SSH "$SUT_HOST" "cd $SUT_DIR && \
        DB_URL='$db_url' DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD \
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
        $SSH "$SUT_HOST" "tail -15 $SUT_DIR/app.log" | sed 's/^/      /'
        stop_variant
        return 1
    fi

    # 3. probe the endpoint this cell will hammer, before measuring it
    local probe="/nodb"
    case "$workload" in
        db)       probe="/db?accountId=12345" ;;
        db-heavy) probe="/db-heavy?accountId=12345" ;;
        db-slow)  probe="/db-slow?accountId=12345" ;;
        api)      probe="/api" ;;
    esac
    local code
    code=$($SSH "$SUT_HOST" "curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
        'http://localhost:8080$probe'" 2>/dev/null)
    if [ "$code" != "200" ]; then
        echo "    FAILED: $probe returned $code (404 means the database is not seeded)"
        stop_variant
        return 1
    fi

    # 4. metrics before
    $SSH "$SUT_HOST" 'curl -s http://localhost:8080/actuator/prometheus' \
        > "$OUT_DIR/$tag.metrics.before.txt"

    # 5. load
    $SSH "$LOADGEN_HOST" "cd $LOADGEN_DIR && \
        BASE_URL=http://$SUT_PRIVATE_IP:8080 RATE=$rate \
        DURATION=$DURATION WARMUP=$WARMUP OUT=$tag.json \
        k6 run --quiet --no-color $workload.js" 2>&1 \
        | grep -vE 'level=(warning|error)' | sed 's/^/    /'

    # 6. metrics after - must happen before the JVM is stopped
    $SSH "$SUT_HOST" 'curl -s http://localhost:8080/actuator/prometheus' \
        > "$OUT_DIR/$tag.metrics.after.txt"

    # 7. stop, then collect
    stop_variant
    $SCP "$LOADGEN_HOST:$LOADGEN_DIR/$tag.json" "$OUT_DIR/" >/dev/null 2>&1 \
        || echo "    WARNING: could not fetch $tag.json"

    # 8. flag cells where k6 could not sustain the offered rate
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

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

[ $# -ge 1 ] || usage
WORKLOAD=$1
SINGLE_RATE=${2:-}

preflight

# Checked here rather than inside preflight: several checks return early when a
# prerequisite is missing, which would skip a test placed at the end of that
# function and report success after a failure.
if [ "$FAILED" -ne 0 ]; then
    echo "preflight failed - fix the above before running cells"
    exit 1
fi
mkdir -p "$OUT_DIR"

if [ "$WORKLOAD" = "check" ]; then
    echo "preflight passed - nothing else to do"
    exit 0
fi

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
