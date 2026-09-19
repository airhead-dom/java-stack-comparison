#!/usr/bin/env bash
# Shared helpers for the benchmark run scripts.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
K6_BIN="${K6_BIN:-/c/Program Files/k6/k6.exe}"
JAVA_BIN="${JAVA_BIN:-${JAVA_HOME:-/c/Program Files/Java/jdk-25.0.4}/bin/java}"
SUT_URL="${SUT_URL:-http://localhost:8080}"
STUB_URL="${STUB_URL:-http://localhost:9099}"

VARIANTS=(mvc-platform mvc-virtual webflux-r2dbc mvc-jpa)

# Held identical across variants -- these mirror the convention plugin's bootRun
# flags, which java -jar does not pick up. Drift here invalidates a comparison.
BENCH_JVM_BASE="${BENCH_JVM_BASE:--Xms1g -Xmx1g -XX:+UseG1GC -XX:+AlwaysPreTouch}"

# Rate ladders, derived in docs/WORKLOADS.md from the measured knees.
declare -A LADDER=(
  [nodb]="1000 2000 4000 8000"
  [db]="400 800 1000 1200 1600 2400"
  [db-heavy]="400 800 1000 1200 1600 2400"
  [db-slow]="50 100 150 200 300 400"
  [api]="250 500 1000 1500 2000"
)

die() { echo "ERROR: $*" >&2; exit 1; }

preflight() {
  [ -x "$K6_BIN" ] || die "k6 not found at $K6_BIN (set K6_BIN)"
  [ -x "$JAVA_BIN" ] || die "java not found at $JAVA_BIN (set JAVA_BIN or JAVA_HOME)"
  curl -sf "$STUB_URL/actuator/health" >/dev/null || die "stub-service not reachable at $STUB_URL"
}

wait_healthy() {
  local url=$1 tries=${2:-120}
  for _ in $(seq 1 "$tries"); do
    curl -sf "$url/actuator/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

start_variant() {
  local variant=$1 log=$2
  local jar="$ROOT/$variant/build/libs/$variant-0.0.1-SNAPSHOT.jar"
  [ -f "$jar" ] || die "missing $jar -- run ./gradlew bootJar"
  # shellcheck disable=SC2086
  "$JAVA_BIN" $BENCH_JVM_BASE ${BENCH_JVM_EXTRA:-} -jar "$jar" > "$log" 2>&1 &
  echo $!
}

# Metric snapshots bracket the measured phase so counters can be differenced
# rather than read as since-startup totals.
snapshot_metrics() {
  curl -sf "$SUT_URL/actuator/prometheus" -o "$1" 2>/dev/null || true
}
