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
# Ubuntu. Needs java, curl and pgrep (procps); only java is not on a stock
# server image.
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
# Pinned rather than left to the default heuristic, which sizes from the box and
# so would differ between the backend and anywhere this is reproduced. The stub
# holds delayed connections, not data; 512m is ample and it is now a constant of
# the experiment rather than a property of the machine.
JVM_FLAGS="${JVM_FLAGS:--Xms512m -Xmx512m -XX:+UseG1GC}"
HEALTH="http://localhost:$PORT/actuator/health"

# Matches the full command line, so it finds the jar however it was started.
pid() { pgrep -f "java.*$JAR" | head -1; }

# The authority on whether the stub is usable. A pid only says a process
# exists; this says it is serving.
alive() { curl -sf --max-time 3 "$HEALTH" >/dev/null 2>&1; }

start() {
    if alive; then
        echo "already running (pid $(pid))"
        return 0
    fi
    [ -f "$JAR" ] || { echo "$JAR not found in $PWD"; return 1; }
    command -v java >/dev/null || { echo "java not on PATH"; return 1; }

    # One inbound socket per in-flight request, for the whole delay: /api-1000
    # at 2,000 rps parks 2,000 of them here at once. Ubuntu's 1024 default would
    # make the stub the bottleneck, which is the one thing it must never be.
    ulimit -n 65535 2>/dev/null || ulimit -n "$(ulimit -Hn)" 2>/dev/null || true
    if [ "$(ulimit -n)" -lt 8192 ]; then
        echo "  WARNING: open file limit is $(ulimit -n); the long-wait"
        echo "           workloads park several thousand connections here"
    fi

    echo "starting $JAR"
    nohup java $JVM_FLAGS -jar "$JAR" > "$LOG" 2>&1 &

    for i in $(seq 1 30); do
        sleep 1
        if alive; then
            echo "up after ${i}s (pid $(pid))"
            return 0
        fi
    done

    echo "failed to start"
    if [ -s "$LOG" ]; then
        echo "last log lines:"
        tail -20 "$LOG" | sed 's/^/  /'
    else
        echo "  $LOG is empty or missing - the JVM did not get far enough to log"
    fi
    return 1
}

stop() {
    local p
    p=$(pid)
    if [ -z "$p" ]; then
        if alive; then
            echo "port $PORT is served but no $JAR process was found"
            echo "something else is listening:"
            ss -lptn "sport = :$PORT" 2>/dev/null | sed 's/^/  /'
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
    # silently turn every /api cell into a measurement of something else. Both
    # delays are checked: honouring 200 does not prove it honours 800, and the
    # long-wait workloads are the ones where a wrong delay would be hardest to
    # spot in the results.
    local ok=0 t
    for want in 0.2 0.8; do
        t=$(curl -s -o /dev/null -w '%{time_total}' --max-time 5 \
            "http://localhost:$PORT/upstream?delayMs=$(awk "BEGIN{print $want*1000}")" 2>/dev/null)
        if awk "BEGIN{exit !(${t:-0} > $want*0.75 && ${t:-0} < $want*2)}" 2>/dev/null; then
            echo "delay:   ok, ${t}s for ${want}s"
        else
            echo "delay:   WRONG - returned in ${t}s, expected ~${want}s"
            ok=1
        fi
    done

    # The runners sample this during every long-wait cell as the witness that
    # the stub was not the bottleneck. Missing, there is no such evidence.
    if curl -sf --max-time 5 "http://localhost:$PORT/actuator/prometheus" >/dev/null 2>&1; then
        echo "metrics: ok on $PORT/actuator/prometheus"
    else
        echo "metrics: MISSING - the long-wait runners cannot sample the stub"
        ok=1
    fi
    return $ok
}

case "${1:-status}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; echo; start ;;
    status)  status ;;
    log)     tail -f "$LOG" ;;
    *)       echo "usage: $0 {start|stop|restart|status|log}"; exit 1 ;;
esac
