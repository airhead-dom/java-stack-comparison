#!/usr/bin/env bash
#
# Start, stop and check the variant under test. Runs ON the SUT, next to the
# jars. Ubuntu. No ssh.
#
#   ./variant.sh start mvc-virtual
#   ./variant.sh stop
#   ./variant.sh restart mvc-virtual
#   ./variant.sh status
#   ./variant.sh list
#   ./variant.sh log
#
# start always kills every other variant first. They all bind 8080 on purpose,
# so two at once means the second fails to start and the load generator keeps
# measuring the first - which looks like a result, not a mistake.

set -uo pipefail
cd "$(dirname "$0")"

BACKEND_IP="${BACKEND_IP:-172.31.3.118}"      # postgres + stub
PORT="${PORT:-8080}"
POOL_SIZE="${POOL_SIZE:-20}"
JVM_FLAGS="${JVM_FLAGS:--Xms1g -Xmx1g -XX:+UseG1GC}"
DB_NAME="${DB_NAME:-bench}"
DB_USER="${DB_USER:-bench}"
DB_PASSWORD="${DB_PASSWORD:-bench}"
LOG="${LOG:-app.log}"

VARIANTS="mvc-platform mvc-virtual webflux-r2dbc mvc-jpa"
HEALTH="http://localhost:$PORT/actuator/health"
METRICS="http://localhost:$PORT/actuator/prometheus"

alive() { curl -sf --max-time 3 "$HEALTH" >/dev/null 2>&1; }

# Which variant is actually serving, according to the app itself.
running_variant() {
    curl -s --max-time 3 "$METRICS" 2>/dev/null \
        | grep -m1 -o 'variant="[^"]*"' | cut -d'"' -f2
}

jar_for() { echo "$1-0.0.1-SNAPSHOT.jar"; }

# webflux uses R2DBC, the rest use JDBC. Same host, different scheme.
db_url_for() {
    if [ "$1" = "webflux-r2dbc" ]; then
        echo "r2dbc:postgresql://$BACKEND_IP:5432/$DB_NAME"
    else
        echo "jdbc:postgresql://$BACKEND_IP:5432/$DB_NAME"
    fi
}

# Kills every variant, whichever is running. Deliberately matches only the four
# known jars, so a stub or anything else sharing this box is left alone.
kill_all() {
    local killed=0 p
    for v in $VARIANTS; do
        for p in $(pgrep -f "java.*$(jar_for "$v")" 2>/dev/null); do
            echo "  killing $v (pid $p)"
            kill "$p" 2>/dev/null
            killed=1
        done
    done
    [ "$killed" -eq 0 ] && return 0

    # Wait for a clean exit, then force. A half-dead JVM still holds the port.
    for _ in $(seq 1 10); do
        sleep 1
        pgrep -f "java.*SNAPSHOT.jar" >/dev/null 2>&1 || { echo "  stopped"; return 0; }
    done
    echo "  did not exit, forcing"
    for v in $VARIANTS; do
        pkill -9 -f "java.*$(jar_for "$v")" 2>/dev/null
    done
    sleep 2
}

# The port can stay bound briefly after the process goes. Starting before it is
# free gives a confusing bind failure inside the next JVM's log.
wait_port_free() {
    for _ in $(seq 1 15); do
        ss -ltn "sport = :$PORT" 2>/dev/null | grep -q ":$PORT" || return 0
        sleep 1
    done
    echo "  WARNING: port $PORT still bound"
    ss -lptn "sport = :$PORT" 2>/dev/null | sed 's/^/    /'
    return 1
}

start() {
    local want="${1:-}"
    if [ -z "$want" ]; then
        echo "which variant? one of: $VARIANTS"
        return 1
    fi
    case " $VARIANTS " in
        *" $want "*) ;;
        *) echo "unknown variant '$want' - one of: $VARIANTS"; return 1 ;;
    esac

    local jar; jar=$(jar_for "$want")
    [ -f "$jar" ] || { echo "$jar not found in $PWD"; return 1; }
    command -v java >/dev/null || { echo "java not on PATH"; return 1; }

    echo "clearing anything already running"
    kill_all
    wait_port_free

    echo "starting $want"
    DB_URL="$(db_url_for "$want")" \
    DB_USER="$DB_USER" \
    DB_PASSWORD="$DB_PASSWORD" \
    UPSTREAM_URL="http://$BACKEND_IP:9099" \
    POOL_SIZE="$POOL_SIZE" \
    nohup java $JVM_FLAGS -jar "$jar" > "$LOG" 2>&1 &

    for i in $(seq 1 90); do
        sleep 1
        if alive; then
            local got; got=$(running_variant)
            # Confirm the app reports the variant that was asked for, rather
            # than trusting that the right jar was started.
            if [ "$got" = "$want" ]; then
                echo "up after ${i}s - serving $got on $PORT"
                return 0
            fi
            echo "up after ${i}s but reports '$got', expected '$want'"
            return 1
        fi
    done

    echo "failed to start - last log lines:"
    tail -20 "$LOG" | sed 's/^/  /'
    return 1
}

stop() {
    if ! pgrep -f "java.*SNAPSHOT.jar" >/dev/null 2>&1; then
        alive && { echo "port $PORT is served but no variant process found:"; \
                   ss -lptn "sport = :$PORT" 2>/dev/null | sed 's/^/  /'; return 1; }
        echo "not running"
        return 0
    fi
    kill_all
    wait_port_free
}

status() {
    if alive; then
        local v p
        v=$(running_variant)
        p=$(pgrep -f "java.*$(jar_for "${v:-nothing}")" 2>/dev/null | head -1)
        echo "variant: ${v:-unknown}${p:+  (pid $p)}"
        echo "health:  ok on $PORT"
        echo "pool:    $(curl -s "$METRICS" | grep -E '^(hikaricp_connections_max|r2dbc_pool_max)' \
                        | head -1 | awk '{print $NF}')"
        return 0
    fi
    if pgrep -f "java.*SNAPSHOT.jar" >/dev/null 2>&1; then
        echo "variant: process exists but $PORT is not answering - still starting, or failed"
        echo "         check the log: $0 log"
        return 1
    fi
    echo "variant: not running"
    return 1
}

list() {
    echo "available in $PWD:"
    for v in $VARIANTS; do
        [ -f "$(jar_for "$v")" ] && echo "  $v" || echo "  $v   (jar missing)"
    done
}

case "${1:-status}" in
    start)   start "${2:-}" ;;
    stop)    stop ;;
    restart) start "${2:-$(running_variant)}" ;;
    status)  status ;;
    list)    list ;;
    log)     tail -f "$LOG" ;;
    *)       echo "usage: $0 {start <variant>|stop|restart [variant]|status|list|log}"
             echo "       variants: $VARIANTS"; exit 1 ;;
esac
