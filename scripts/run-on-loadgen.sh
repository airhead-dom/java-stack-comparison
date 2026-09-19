#!/usr/bin/env bash
#
# Runs the benchmark FROM the load generator, inside the VPC.
#
# Copy this to the load generator along with the scenarios, and run it there:
#
#   scp -i key.pem scripts/run-on-loadgen.sh ubuntu@<loadgen-public>:~/
#   ssh -i key.pem ubuntu@<loadgen-public>
#   ./run-on-loadgen.sh check
#   ./run-on-loadgen.sh api
#
# Every ssh hop is then same-AZ (sub-millisecond) instead of crossing the
# internet from your laptop, and k6 runs locally with no hop at all. The
# laptop version of this script pays ~200ms of round trip on every single
# command, which is most of why it feels slow.
#
# Results land in ~/results on this box. Fetch them at the end with:
#   scp -i key.pem 'ubuntu@<loadgen-public>:results/*' results/raw/

set -uo pipefail

# ---------------------------------------------------------------------------
# CONFIG - edit these
# ---------------------------------------------------------------------------
SUT_IP="${SUT_IP:-172.31.15.61}"          # private ip of the app server
BACKEND_IP="${BACKEND_IP:-172.31.3.118}"  # private ip of postgres + stub

SSH_USER="${SSH_USER:-ubuntu}"
KEY="${KEY:-$HOME/.ssh/myec.pem}"         # key ON THIS BOX; leave empty to use
                                          # a forwarded agent (ssh -A)

SCENARIO_DIR="${SCENARIO_DIR:-$HOME/scenarios}"
RESULT_DIR="${RESULT_DIR:-$HOME/results}"
SUT_DIR="${SUT_DIR:-\$HOME}"              # variant jars, on the SUT
BACKEND_DIR="${BACKEND_DIR:-\$HOME}"      # stub jar, on the backend
STUB_JAR="${STUB_JAR:-stub-service-0.0.1-SNAPSHOT.jar}"

DB_NAME="${DB_NAME:-bench}"
DB_USER="${DB_USER:-bench}"
DB_PASSWORD="${DB_PASSWORD:-bench}"
EXPECTED_ACCOUNTS="${EXPECTED_ACCOUNTS:-200000}"

REPS="${REPS:-3}"
DURATION="${DURATION:-60s}"
WARMUP="${WARMUP:-60s}"
POOL_SIZE="${POOL_SIZE:-20}"
JVM_FLAGS="${JVM_FLAGS:--Xms1g -Xmx1g -XX:+UseG1GC}"

VARIANTS="${VARIANTS:-mvc-platform mvc-virtual webflux-r2dbc mvc-jpa}"

RATES_nodb="1000 2000 4000 8000"
RATES_db="400 800 1000 1200 1600 2400"
RATES_db_heavy="400 800 1000 1200 1600 2400"
RATES_db_slow="50 100 150 200 300 400"
RATES_api="250 500 1000 1500 2000"

# ---------------------------------------------------------------------------

# One multiplexed connection per host, reused for every command. Without this
# each ssh call pays a fresh TCP and crypto handshake, which dominates the
# runtime when a cell issues a dozen of them.
CTRL_DIR="${TMPDIR:-/tmp}/bench-ssh-$$"
mkdir -p "$CTRL_DIR"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 \
          -o ControlMaster=auto -o ControlPath=$CTRL_DIR/%C -o ControlPersist=10m"
[ -n "$KEY" ] && SSH_OPTS="-i $KEY $SSH_OPTS"

SUT="$SSH_USER@$SUT_IP"
BACKEND="$SSH_USER@$BACKEND_IP"
FAILED=0

sut()     { ssh $SSH_OPTS "$SUT" "$@"; }
backend() { ssh $SSH_OPTS "$BACKEND" "$@"; }

cleanup() { ssh $SSH_OPTS -O exit "$SUT" 2>/dev/null; \
            ssh $SSH_OPTS -O exit "$BACKEND" 2>/dev/null; rm -rf "$CTRL_DIR"; }
trap cleanup EXIT

usage() {
    echo "usage: $0 <workload|all|check> [rate]"
    echo "  workloads: nodb db db-heavy db-slow api"
    exit 1
}

rates_for() { local k="RATES_${1//-/_}"; echo "${!k:-}"; }

db_url_for() {
    if [ "$1" = "webflux-r2dbc" ]; then
        echo "r2dbc:postgresql://$BACKEND_IP:5432/$DB_NAME"
    else
        echo "jdbc:postgresql://$BACKEND_IP:5432/$DB_NAME"
    fi
}

ok()   { printf '  %-40s OK    %s\n' "$1" "${2:-}"; }
bad()  { printf '  %-40s FAIL  %s\n' "$1" "${2:-}"; FAILED=1; }
warn() { printf '  %-40s WARN  %s\n' "$1" "${2:-}"; }

# --- stub lifecycle --------------------------------------------------------

stub_alive() {
    curl -sf --max-time 5 "http://$BACKEND_IP:9099/actuator/health" >/dev/null 2>&1
}

ensure_stub() {
    local indent="${1:-  }"
    stub_alive && return 0
    echo "${indent}stub is down - starting it on $BACKEND_IP"
    backend "test -f $BACKEND_DIR/$STUB_JAR" 2>/dev/null \
        || { echo "${indent}$STUB_JAR not found in $BACKEND_DIR"; return 1; }
    backend "cd $BACKEND_DIR && nohup java -jar $STUB_JAR > stub.log 2>&1 &" >/dev/null 2>&1
    for i in $(seq 1 30); do
        sleep 2
        stub_alive && { echo "${indent}stub up after $((i * 2))s"; return 0; }
    done
    echo "${indent}stub failed to start - last log lines:"
    backend "tail -15 $BACKEND_DIR/stub.log" 2>/dev/null | sed "s/^/${indent}  /"
    return 1
}

# --- preflight -------------------------------------------------------------

preflight() {
    echo "preflight"

    command -v k6 >/dev/null \
        && ok "k6 here" "$(k6 version 2>/dev/null | head -1)" \
        || bad "k6 here" "not installed or not on PATH"

    local missing=""
    for wl in nodb db db-heavy db-slow api; do
        [ -f "$SCENARIO_DIR/$wl.js" ] || missing="$missing $wl.js"
    done
    [ -z "$missing" ] && ok "scenarios" "5 files in $SCENARIO_DIR" \
                      || bad "scenarios" "missing:$missing"

    [ -f "$SCENARIO_DIR/../lib/common.js" ] \
        && ok "lib/common.js" \
        || bad "lib/common.js" "scenarios import ../lib/common.js"

    local u
    u=$(sut 'uname -sm' 2>/dev/null)
    [ -n "$u" ] && ok "ssh to SUT" "$u" || { bad "ssh to SUT" "$SUT unreachable"; return; }

    local jv
    jv=$(sut 'java -version 2>&1 | head -1' 2>/dev/null)
    [ -n "$jv" ] && ok "java on SUT" "$jv" || bad "java on SUT" "not found"

    for v in $VARIANTS; do
        sut "test -f $SUT_DIR/$v-0.0.1-SNAPSHOT.jar" \
            && ok "jar: $v" || bad "jar: $v" "missing from $SUT_DIR"
    done

    # Postgres, reached from the SUT - the path the application uses.
    sut "timeout 5 bash -c '</dev/tcp/$BACKEND_IP/5432'" 2>/dev/null \
        && ok "postgres open from SUT" "$BACKEND_IP:5432" \
        || bad "postgres open from SUT" "refused - check the security group"

    if sut 'command -v psql >/dev/null'; then
        local rows
        rows=$(sut "PGPASSWORD=$DB_PASSWORD psql -h $BACKEND_IP -U $DB_USER -d $DB_NAME \
            -tAc 'select count(*) from accounts'" 2>/dev/null | tr -d '\r ')
        if [ -z "${rows:-}" ]; then
            bad "postgres query" "port open but query failed - credentials or db name?"
        elif [ "$rows" -ge "$EXPECTED_ACCOUNTS" ] 2>/dev/null; then
            ok "postgres seeded" "$rows accounts"
        else
            bad "postgres seeded" "only $rows accounts, expected $EXPECTED_ACCOUNTS"
        fi
    else
        warn "postgres seeded" "psql not on the SUT, cannot verify"
    fi

    if stub_alive; then ok "stub" "$BACKEND_IP:9099"
    elif ensure_stub "    "; then ok "stub" "$BACKEND_IP:9099 (started)"
    else bad "stub" "down and could not be started"; fi

    # Verify by measuring, not by trusting health: a stub that ignores delayMs
    # would pass a health check and invalidate every /api cell.
    local t
    t=$(curl -s -o /dev/null -w '%{time_total}' --max-time 5 \
        "http://$BACKEND_IP:9099/upstream?delayMs=200" 2>/dev/null)
    awk "BEGIN{exit !(${t:-0} > 0.15)}" 2>/dev/null \
        && ok "stub delays correctly" "${t}s for delayMs=200" \
        || bad "stub delays correctly" "returned in ${t}s, expected ~0.2s"

    echo
}

# --- one cell --------------------------------------------------------------

stop_variant() { sut 'pkill -f "SNAPSHOT.jar" || true' >/dev/null 2>&1; }

run_cell() {
    local variant=$1 workload=$2 rate=$3 rep=$4
    local tag="${variant}__${workload}__${rate}rps__r${rep}"
    local db_url; db_url=$(db_url_for "$variant")

    echo "--- $tag"

    if [ "$workload" = "api" ]; then
        ensure_stub "    " || { echo "    SKIPPED: stub down"; return 1; }
    else
        sut "timeout 5 bash -c '</dev/tcp/$BACKEND_IP/5432'" 2>/dev/null \
            || { echo "    SKIPPED: postgres down"; return 1; }
    fi

    local probe="/nodb"
    case "$workload" in
        db)       probe="/db?accountId=12345" ;;
        db-heavy) probe="/db-heavy?accountId=12345" ;;
        db-slow)  probe="/db-slow?accountId=12345" ;;
        api)      probe="/api" ;;
    esac

    # Start, wait for health, and probe the endpoint in ONE ssh session. The
    # laptop version opened a fresh connection for every poll, which is what
    # made it crawl.
    local result
    result=$(sut "cd $SUT_DIR && \
        DB_URL='$db_url' DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD \
        UPSTREAM_URL='http://$BACKEND_IP:9099' POOL_SIZE=$POOL_SIZE \
        nohup java $JVM_FLAGS -jar $variant-0.0.1-SNAPSHOT.jar > app.log 2>&1 &
        for i in \$(seq 1 90); do
            curl -sf http://localhost:8080/actuator/health >/dev/null 2>&1 && break
            sleep 1
        done
        curl -sf http://localhost:8080/actuator/health >/dev/null 2>&1 || { echo 'NOSTART'; exit 0; }
        curl -s -o /dev/null -w 'CODE:%{http_code}' --max-time 10 'http://localhost:8080$probe'" 2>/dev/null)

    if echo "$result" | grep -q NOSTART; then
        echo "    FAILED to start - last log lines:"
        sut "tail -15 $SUT_DIR/app.log" | sed 's/^/      /'
        stop_variant; return 1
    fi
    local code="${result#*CODE:}"
    if [ "$code" != "200" ]; then
        echo "    FAILED: $probe returned $code (404 means the database is not seeded)"
        stop_variant; return 1
    fi

    mkdir -p "$RESULT_DIR"
    sut 'curl -s http://localhost:8080/actuator/prometheus' > "$RESULT_DIR/$tag.metrics.before.txt"

    ( cd "$SCENARIO_DIR" && \
      BASE_URL="http://$SUT_IP:8080" RATE="$rate" DURATION="$DURATION" WARMUP="$WARMUP" \
      OUT="$RESULT_DIR/$tag.json" \
      k6 run --quiet --no-color "$workload.js" ) 2>&1 \
      | grep -vE 'level=(warning|error)' | sed 's/^/    /'

    # Must happen before the JVM is stopped.
    sut 'curl -s http://localhost:8080/actuator/prometheus' > "$RESULT_DIR/$tag.metrics.after.txt"
    stop_variant

    if [ -f "$RESULT_DIR/$tag.json" ]; then
        local dropped
        dropped=$(python3 -c "
import json,sys
m=json.load(open(sys.argv[1]))['metrics']
print(int(m.get('dropped_iterations{scenario:measure}',{}).get('values',{}).get('count',0)))
" "$RESULT_DIR/$tag.json" 2>/dev/null || echo 0)
        if [ "${dropped:-0}" -gt 0 ]; then
            echo "    INVALID: $dropped iterations dropped during measurement"
            touch "$RESULT_DIR/$tag.INVALID"
        fi
    fi
    sleep 5
}

# --- main ------------------------------------------------------------------

[ $# -ge 1 ] || usage
WORKLOAD=$1
SINGLE_RATE=${2:-}

preflight
if [ "$FAILED" -ne 0 ]; then
    echo "preflight failed - fix the above before running cells"
    exit 1
fi
[ "$WORKLOAD" = "check" ] && { echo "preflight passed"; exit 0; }

mkdir -p "$RESULT_DIR"

CELLS=()
if [ "$WORKLOAD" = "all" ]; then WORKLOADS="nodb db db-heavy db-slow api";
else WORKLOADS="$WORKLOAD"; fi

for wl in $WORKLOADS; do
    if [ -n "$SINGLE_RATE" ]; then rates="$SINGLE_RATE"
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

# Shuffled so drift over a long run cannot correlate with one variant.
mapfile -t CELLS < <(printf '%s\n' "${CELLS[@]}" | shuf)

echo "${#CELLS[@]} cells"
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
echo "results in $RESULT_DIR/"
# Relative to the remote home directory on purpose: scp speaks SFTP in
# OpenSSH 9+, which does not expand ~ or $HOME.
echo "fetch with:  scp -i key.pem '$SSH_USER@<loadgen-public>:results/*' results/raw/"
