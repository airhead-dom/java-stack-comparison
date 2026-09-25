#!/usr/bin/env bash
#
# Runs the api-1000 rate ladder against whatever variant is currently running on
# the SUT. One 1,000ms upstream call and no database, so the scarce resource is
# requests in flight rather than threads - and at a one-second delay the offered
# rate and the in-flight count are the same number.
#
# Start a variant on the app server yourself first, then run this here:
#
#   ./run-api-1000.sh              # the whole ladder
#   ./run-api-1000.sh 1000         # one rate
#
# Only mvc-virtual and webflux-r2dbc are worth running. 200 Tomcat threads over
# a one-second hold cap mvc-platform at 200 rps, below the bottom rung.
#
# No ssh. It touches the SUT's HTTP port, the stub's, and k6.

set -uo pipefail
cd "$(dirname "$0")"

SUT="${SUT:-172.31.15.61}"
BACKEND="${BACKEND:-172.31.3.118}"        # the stub, sampled as a witness
WORKLOAD="api-1000"
SCRIPT="api-1000.js"
LATENCY_S="1.010"                         # healthy latency, for the VU estimate
TIMEOUT_S="2.5"                           # must match timeoutMs in $SCRIPT
VU_MARGIN="1.3"                           # must match vuMargin in $SCRIPT

RATES="${1:-500 1000 1500 2000}"
REPS="${REPS:-2}"
DURATION="${DURATION:-60s}"
WARMUP="${WARMUP:-60s}"
OUTDIR="${OUTDIR:-$HOME/results}"
SAMPLE_EVERY="${SAMPLE_EVERY:-2}"         # seconds between mid-run samples
VU_MB="${VU_MB:-2}"                       # measured cost of a k6 VU
RESERVE_MB="${RESERVE_MB:-1024}"          # left for the OS and k6 itself

BASE="http://$SUT:8080"
STUB="http://$BACKEND:9099"
mkdir -p "$OUTDIR"

command -v k6 >/dev/null || { echo "k6 not on PATH"; exit 1; }
# Used to detect dropped iterations. Without it, a cell that failed to sustain
# the offered rate would be recorded as though it were valid.
command -v python3 >/dev/null || { echo "python3 not on PATH (apt install -y python3)"; exit 1; }
[ -f "$SCRIPT" ] || { echo "$SCRIPT not found in $PWD"; exit 1; }
# Every scenario imports this. Without it k6 fails at parse, once per cell.
[ -f ../lib/common.js ] || { echo "../lib/common.js not found - copy load/lib across too"; exit 1; }

# Ubuntu defaults to 1024 open files. This workload holds one socket per request
# in flight for the whole delay - ~2,000 at the top rung - so the limit binds
# here long before anything else does.
ulimit -n 65535 2>/dev/null || ulimit -n "$(ulimit -Hn)" 2>/dev/null || true
if [ "$(ulimit -n)" -lt 8192 ]; then
    echo "WARNING: open file limit is $(ulimit -n); high rates may fail with"
    echo "         too many open files. Raise it in /etc/security/limits.conf."
fi

# Ask the app which variant it is rather than being told. Every metric carries a
# variant tag, so a result cannot be mislabelled by having started the wrong jar.
VARIANT=$(curl -s --max-time 5 "$BASE/actuator/prometheus" | grep -m1 -o 'variant="[^"]*"' | cut -d'"' -f2)
if [ -z "$VARIANT" ]; then
    echo "nothing answering at $BASE - start a variant on the app server first"
    exit 1
fi

# The endpoint has to exist. mvc-platform and mvc-jpa were never given it, and
# without this check every cell would quietly record 404s as a result.
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/$WORKLOAD")
if [ "$code" != "200" ]; then
    echo "$BASE/$WORKLOAD returned $code, not 200"
    echo "  - $VARIANT may not implement it (only mvc-virtual and webflux-r2dbc do)"
    echo "  - or the stub is down; check with ./stub.sh status on the backend box"
    exit 1
fi

# The stub is what produces the delay. If it is not answering, every cell
# measures connection refusals and the k6 output still looks like a result.
if ! curl -sf --max-time 5 "$STUB/actuator/health" >/dev/null 2>&1; then
    echo "WARNING: no stub health at $STUB - the witness samples will be empty"
    STUB=""
fi

echo "variant:  $VARIANT"
echo "workload: $WORKLOAD"
echo "rates:    $RATES   x $REPS reps"
echo "memory:   $(awk '/MemAvailable/ {printf "%.1fGB available", $2/1048576}' /proc/meminfo)"
echo

# One CSV row per sample, for the whole cell. The before/after scrape pair the
# other runners take is useless for a gauge: both are taken while the system is
# idle, so in-flight reads 0 and heap reads wherever GC happened to leave it.
# What this workload exists to measure is the in-flight count DURING load, so it
# has to be sampled during load.
#
# in_flight is every request the SUT has in progress, less one for this scrape:
# Micrometer's active-request timer publishes a single series labelled
# uri="UNKNOWN" whatever the endpoint - an in-flight request has no resolved uri
# or outcome yet - so it cannot be filtered per endpoint. A cell runs one
# workload, so the total is that workload's in-flight count. active_raw keeps
# the uncorrected reading so the adjustment stays visible.
sample_header() { echo "t_s,in_flight,active_raw,heap_used_b,live_data_b,cpu,threads_live,files_open"; }

sample_once() {
    curl -s --max-time "$SAMPLE_EVERY" "$1/actuator/prometheus" | awk -v T="$2" '
        # The value is the last field: label values may contain spaces, as in
        # id="G1 Eden Space".
        /^jvm_memory_used_bytes\{area="heap"/          { heap += $NF }
        /^http_server_requests_active_seconds_count\{/ { active += $NF }
        /^jvm_gc_live_data_size_bytes/                 { live = $NF }
        /^process_cpu_usage/                           { cpu = $NF }
        /^jvm_threads_live_threads/                    { threads = $NF }
        /^process_files_open_files/                    { files = $NF }
        END { inflight = active - 1            # this scrape is itself in flight
              if (inflight < 0) inflight = 0
              printf "%s,%d,%d,%.0f,%.0f,%s,%d,%d\n",
                     T, inflight, active, heap, live, (cpu == "" ? 0 : cpu), threads, files }'
}

# Runs until killed. Sampling costs one actuator request every couple of seconds
# against a system serving thousands, which is not a perturbation worth
# correcting for.
sampler() {
    local target="$1" out="$2" t=0
    sample_header > "$out"
    while true; do
        sample_once "$target" "$t" >> "$out"
        t=$((t + SAMPLE_EVERY))
        sleep "$SAMPLE_EVERY"
    done
}

for rate in $RATES; do
    for rep in $(seq 1 "$REPS"); do
        tag="${VARIANT}__${WORKLOAD}__${rate}rps__r${rep}"
        echo "--- $tag"

        # What k6 will ask for, computed the way ../lib/common.js computes it.
        # preAlloc is created up front and must fit. maxVUs is only a ceiling,
        # but this is an overload test and an overloaded cell really does grow
        # into it; a generator that dies mid-ladder loses every cell after it.
        read -r prealloc maxvus <<EOF
$(awk -v r="$rate" -v l="$LATENCY_S" -v t="$TIMEOUT_S" -v m="$VU_MARGIN" \
      'BEGIN { p = int(r * l * m) + 1; c = int(r * t * 1.2) + 1
               if (p < 100) p = 100
               print p, (c > p ? c : p) }')
EOF
        avail_mb=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
        budget_vus=$(( (avail_mb - RESERVE_MB) / VU_MB ))

        if [ "$budget_vus" -lt "$prealloc" ]; then
            echo "    SKIPPED: needs $prealloc VUs pre-allocated (~$((prealloc * VU_MB))MB)"
            echo "             but only ${avail_mb}MB is available, ${RESERVE_MB}MB reserved."
            echo "             This cell cannot be measured on this generator."
            touch "$OUTDIR/$tag.SKIPPED"
            continue
        fi

        # Pre-allocation fits but the ceiling does not: hand k6 a budget so it
        # clamps rather than growing past the memory it has. A clamped cell that
        # then cannot offer its rate drops iterations and is marked INVALID
        # below, which is a truthful outcome. An OOM is not.
        budget_env=""
        if [ "$budget_vus" -lt "$maxvus" ]; then
            echo "    NOTE: maxVUs $maxvus exceeds what fits ($budget_vus); clamping"
            budget_env="$budget_vus"
        fi

        curl -s "$BASE/actuator/prometheus" > "$OUTDIR/$tag.metrics.before.txt"

        sampler "$BASE" "$OUTDIR/$tag.samples.csv" &
        sampler_pid=$!
        stub_pid=""
        if [ -n "$STUB" ]; then
            sampler "$STUB" "$OUTDIR/$tag.stub.csv" &
            stub_pid=$!
        fi

        # k6 writes the summary beside the scenario, then it is moved. Handing
        # handleSummary an absolute path is untested and would fail silently.
        BASE_URL="$BASE" RATE="$rate" DURATION="$DURATION" WARMUP="$WARMUP" \
        VU_BUDGET="$budget_env" OUT="$tag.json" \
            k6 run --quiet --no-color "$SCRIPT" 2>&1 | grep -vE 'level=(warning|error)' | sed 's/^/    /'

        kill "$sampler_pid" 2>/dev/null; wait "$sampler_pid" 2>/dev/null
        if [ -n "$stub_pid" ]; then
            kill "$stub_pid" 2>/dev/null; wait "$stub_pid" 2>/dev/null
        fi

        if [ -s "$tag.json" ]; then
            mv -f "$tag.json" "$OUTDIR/$tag.json"
        else
            echo "    WARNING: k6 wrote no summary for this cell"
            rm -f "$tag.json"
        fi

        # Taken while the JVM is still up. This data is gone once it stops.
        curl -s "$BASE/actuator/prometheus" > "$OUTDIR/$tag.metrics.after.txt"

        # The headline number for this workload, straight off the samples.
        awk -F, 'NR > 1 && $2 > 0 { n++; s += $2; h += $4; if ($2 > m) m = $2 }
                 END { if (n) printf "    in flight         %d mean, %d peak   |  heap %.0fMB mean\n",
                                     s/n, m, h/n/1048576 }' "$OUTDIR/$tag.samples.csv"

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
