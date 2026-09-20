#!/usr/bin/env bash
#
# Start, stop and check the stub service. Runs ON the backend box, next to the
# jar. No ssh.
#
#   ./stub.sh start
#   ./stub.sh stop
#   ./stub.sh restart
#   ./stub.sh status
#   ./stub.sh log
#
# The stub is the fake downstream that /api calls. If it dies mid-run, every
# /api cell afterwards measures connection refusals instead of the application,
# and the k6 output looks like a result rather than a failure - so check status
# before a run and restart it if in doubt.

set -uo pipefail
cd "$(dirname "$0")"

JAR="${JAR:-stub-service-0.0.1-SNAPSHOT.jar}"
PORT="${PORT:-9099}"
LOG="${LOG:-stub.log}"
HEALTH="http://localhost:$PORT/actuator/health"

# pgrep is not everywhere (Git Bash, minimal images), so fall back to ps. The
# bracket around the first letter stops the grep matching its own command line.
pid() {
    if command -v pgrep >/dev/null 2>&1; then
        pgrep -f "$JAR" | head -1
    else
        ps -ef 2>/dev/null | grep "[j]ava.*$JAR" | awk '{print $2}' | head -1
    fi
}

# The authority on whether the stub is usable. A pid only says a process
# exists; this says it is serving.
alive() { curl -sf --max-time 3 "$HEALTH" >/dev/null 2>&1; }

start() {
    if alive; then
        echo "already running (pid $(pid))"
        return 0
    fi
    [ -f "$JAR" ] || { echo "$JAR not found in $PWD"; return 1; }

    echo "starting $JAR"
    nohup java -jar "$JAR" > "$LOG" 2>&1 &

    for i in $(seq 1 30); do
        sleep 1
        if alive; then
            echo "up after ${i}s (pid $(pid))"
            return 0
        fi
    done

    echo "failed to start - last log lines:"
    tail -20 "$LOG" | sed 's/^/  /'
    return 1
}

stop() {
    local p
    p=$(pid)
    if [ -z "$p" ]; then
        if alive; then
            echo "port $PORT is served but no matching process was found"
            echo "something other than $JAR is listening - check by hand"
            return 1
        fi
        echo "not running"
        return 0
    fi

    echo "stopping pid $p"
    kill "$p" 2>/dev/null

    # Give it a chance to shut down cleanly before forcing it.
    for _ in $(seq 1 10); do
        sleep 1
        [ -z "$(pid)" ] && { echo "stopped"; return 0; }
    done

    echo "did not exit, forcing"
    kill -9 "$p" 2>/dev/null
    sleep 1
    [ -z "$(pid)" ] && echo "stopped" || echo "STILL RUNNING - check by hand"
}

status() {
    local p
    p=$(pid)

    # Health first, pid second: what matters is whether the port is served, and
    # the pid lookup can miss a process started a different way.
    if alive; then
        echo "stub:    running${p:+, pid $p}"
        echo "health:  ok on $PORT"
    elif [ -n "$p" ]; then
        echo "stub:    process $p exists but $PORT is not answering"
        echo "         check the log: $0 log"
        return 1
    else
        echo "stub:    not running"
        return 1
    fi

    # Health alone is not enough. A stub that answers but ignores delayMs would
    # silently turn every /api cell into a measurement of something else.
    local t
    t=$(curl -s -o /dev/null -w '%{time_total}' --max-time 5 \
        "http://localhost:$PORT/upstream?delayMs=200" 2>/dev/null)
    if awk "BEGIN{exit !(${t:-0} > 0.15)}" 2>/dev/null; then
        echo "delay:   ok, ${t}s for delayMs=200"
    else
        echo "delay:   WRONG - returned in ${t}s, expected ~0.2s"
        return 1
    fi
}

case "${1:-status}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; echo; start ;;
    status)  status ;;
    log)     tail -f "$LOG" ;;
    *)       echo "usage: $0 {start|stop|restart|status|log}"; exit 1 ;;
esac
