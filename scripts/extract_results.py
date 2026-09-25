#!/usr/bin/env python3
"""Pull every cell in results/raw/ into one structured dataset.

    python scripts/extract_results.py            # summary tables to stdout
    python scripts/extract_results.py --json     # the raw dataset

Each cell contributes two halves: the k6 JSON (client-side latency, errors,
dropped iterations) and a pair of Prometheus scrapes taken either side of the
measured window (server-side CPU, memory, threads, pool, per-endpoint counts).

Counters are differenced between the two scrapes. That matters here because the
variant's JVM stayed up across a whole ladder rather than restarting per cell,
so a raw reading is a since-startup total covering other workloads too.
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

RAW = "results/raw"
CELL = re.compile(r"(.+?)__(.+?)__(\d+)rps__r(\d+)$")
VARIANT_ORDER = ["webflux-r2dbc", "mvc-virtual", "mvc-platform"]
# Hibernate was a control for a question that is no longer being asked, and it
# was never run on the two workloads that separate the candidates. Its raw cells
# are still on disk; load(all_variants=True) brings them back.
EXCLUDED_VARIANTS = {"mvc-jpa"}
WORKLOAD_ORDER = ["nodb", "db", "db-heavy", "db-slow", "api"]


def parse_prom(path):
    """Prometheus text -> {name: [(labels_dict, value)]}. Value is the last
    field because label values may contain spaces (id="G1 Eden Space")."""
    out = defaultdict(list)
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return out
    for line in text.splitlines():
        if not line or line[0] == "#":
            continue
        try:
            head, value = line.rsplit(None, 1)
            value = float(value)
        except ValueError:
            continue
        if "{" in head:
            name, labelstr = head.split("{", 1)
            labels = dict(re.findall(r'(\w+)="([^"]*)"', labelstr))
        else:
            name, labels = head, {}
        out[name.strip()].append((labels, value))
    return out


def one(prom, name, **match):
    """Single value for a metric, optionally filtered by labels."""
    for labels, value in prom.get(name, []):
        if all(labels.get(k) == v for k, v in match.items()):
            return value
    return None


def total(prom, name, **match):
    """Sum every series of a metric, optionally filtered."""
    vals = [v for labels, v in prom.get(name, [])
            if all(labels.get(k) == val for k, val in match.items())]
    return sum(vals) if vals else None


def delta(a, b, name, **match):
    """after - before for a counter."""
    x, y = total(b, name, **match), total(a, name, **match)
    return None if x is None or y is None else x - y


def ratio(num, den):
    return None if num is None or den in (None, 0) else num / den


def read_cell(path):
    base = os.path.basename(path)[:-len(".json")]
    m = CELL.match(base)
    if not m:
        return None
    variant, workload, rate, rep = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))

    with open(path) as fh:
        doc = json.load(fh)
    mt = doc["metrics"]

    def vals(metric, *keys):
        v = mt.get(metric, {}).get("values", {})
        return {k: v.get(k) for k in keys}

    dur = mt.get("http_req_duration{phase:measure}", mt.get("http_req_duration", {})).get("values", {})
    cell = {
        "variant": variant, "workload": workload, "rate": rate, "rep": rep, "tag": base,
        "invalid": os.path.exists(os.path.join(RAW, base + ".INVALID")),
        "run_ms": doc.get("state", {}).get("testRunDurationMs"),
        # client side, measured phase where the sub-metric exists
        "p50": dur.get("p(50)"), "p95": dur.get("p(95)"), "p99": dur.get("p(99)"),
        "p999": dur.get("p(99.9)"), "max": dur.get("max"), "min": dur.get("min"),
        "avg": dur.get("avg"),
        "err_rate": (mt.get("http_req_failed{phase:measure}", {}).get("values", {}).get("rate")),
        "err_fails": (mt.get("http_req_failed{phase:measure}", {}).get("values", {}).get("fails")),
        "err_passes": (mt.get("http_req_failed{phase:measure}", {}).get("values", {}).get("passes")),
        # http_reqs has no phase sub-metric in these runs: count spans warmup too
        "reqs_total": mt.get("http_reqs", {}).get("values", {}).get("count"),
        "reqs_rate": mt.get("http_reqs", {}).get("values", {}).get("rate"),
        "dropped": mt.get("dropped_iterations{scenario:measure}", {}).get("values", {}).get("count", 0),
        "vus_max": mt.get("vus_max", {}).get("values", {}).get("max"),
        # latency decomposition
        "waiting": vals("http_req_waiting", "avg", "p(50)", "p(95)", "p(99)", "max"),
        "blocked": vals("http_req_blocked", "avg", "p(50)", "p(95)", "p(99)", "max"),
        "connecting": vals("http_req_connecting", "avg", "p(95)", "max"),
        "sending": vals("http_req_sending", "avg", "p(95)", "max"),
        "receiving": vals("http_req_receiving", "avg", "p(95)", "max"),
        "iteration": vals("iteration_duration", "avg", "p(95)", "max"),
        "data_recv_rate": mt.get("data_received", {}).get("values", {}).get("rate"),
    }

    before = parse_prom(os.path.join(RAW, base + ".metrics.before.txt"))
    after = parse_prom(os.path.join(RAW, base + ".metrics.after.txt"))
    if not after:
        return cell

    # Wall time from the JVM's own uptime, not k6's: it brackets exactly the
    # window the counters were differenced over.
    wall = delta(before, after, "process_uptime_seconds")
    cpu_ns = delta(before, after, "process_cpu_time_ns_total")
    cell["srv"] = {
        "wall_s": wall,
        "cpu_s": None if cpu_ns is None else cpu_ns / 1e9,
        "cores": ratio(None if cpu_ns is None else cpu_ns / 1e9, wall),
        "cpu_count": one(after, "system_cpu_count"),
        "heap_mb": ratio(total(after, "jvm_memory_used_bytes", area="heap"), 2 ** 20),
        "heap_max_mb": ratio(one(after, "jvm_memory_max_bytes", area="heap", id="G1 Old Gen"), 2 ** 20),
        "nonheap_mb": ratio(total(after, "jvm_memory_used_bytes", area="nonheap"), 2 ** 20),
        "live_data_mb": ratio(one(after, "jvm_gc_live_data_size_bytes"), 2 ** 20),
        "threads_live": one(after, "jvm_threads_live_threads"),
        "threads_peak": one(after, "jvm_threads_peak_threads"),
        "threads_started": delta(before, after, "jvm_threads_started_threads_total"),
        "threads_blocked": one(after, "jvm_threads_states_threads", state="blocked"),
        "gc_pause_s": delta(before, after, "jvm_gc_pause_seconds_sum"),
        "gc_count": delta(before, after, "jvm_gc_pause_seconds_count"),
        "gc_overhead": one(after, "jvm_gc_overhead"),
        "alloc_gb": ratio(delta(before, after, "jvm_gc_memory_allocated_bytes_total"), 2 ** 30),
        "jvm_version": next((l.get("version") for l, _ in after.get("jvm_info", [])), None),
        # pools - Hikari on the blocking variants, R2DBC on the reactive one
        "pool_max": one(after, "hikaricp_connections_max") or one(after, "r2dbc_pool_max_allocated_connections"),
        "pool_pending": one(after, "hikaricp_connections_pending") or one(after, "r2dbc_pool_pending_connections"),
        "pool_timeouts": delta(before, after, "hikaricp_connections_timeout_total"),
    }
    # Connection hold and acquire time, differenced over the window
    for src, dest in (("usage", "hold_ms"), ("acquire", "acquire_ms")):
        s = delta(before, after, f"hikaricp_connections_{src}_seconds_sum")
        c = delta(before, after, f"hikaricp_connections_{src}_seconds_count")
        cell["srv"][dest] = None if not c else s / c * 1000
        if dest == "hold_ms":
            cell["srv"]["borrows"] = c

    # Per-endpoint server-side outcome, differenced
    uri = "/" + workload
    ep = {}
    for outcome in ("SUCCESS", "SERVER_ERROR", "CLIENT_ERROR"):
        n = delta(before, after, "http_server_requests_seconds_count", uri=uri, outcome=outcome)
        t = delta(before, after, "http_server_requests_seconds_sum", uri=uri, outcome=outcome)
        if n:
            ep[outcome] = {"count": n, "mean_ms": ratio(t, n) * 1000 if t else None}
    exc = {}
    for labels, _ in after.get("http_server_requests_seconds_count", []):
        e = labels.get("exception", "none")
        if labels.get("uri") == uri and e != "none":
            d = delta(before, after, "http_server_requests_seconds_count", uri=uri, exception=e)
            if d:
                exc[e] = d
    cell["srv"]["endpoint"] = ep
    cell["srv"]["exceptions"] = exc
    return cell


def load(all_variants=False):
    cells = [c for c in (read_cell(p) for p in sorted(glob.glob(f"{RAW}/*.json"))) if c]
    if not all_variants:
        cells = [c for c in cells if c["variant"] not in EXCLUDED_VARIANTS]
    cells.sort(key=lambda c: (WORKLOAD_ORDER.index(c["workload"]) if c["workload"] in WORKLOAD_ORDER else 9,
                              c["rate"],
                              VARIANT_ORDER.index(c["variant"]) if c["variant"] in VARIANT_ORDER else 9,
                              c["rep"]))
    return cells


def fmt(x, p=1):
    return "-" if x is None else f"{x:,.{p}f}"


def main():
    cells = load()
    if "--json" in sys.argv:
        json.dump(cells, sys.stdout, indent=1, default=str)
        return

    print(f"{len(cells)} cells, {sum(1 for c in cells if c['invalid'])} marked invalid\n")
    cur = None
    for c in cells:
        key = (c["workload"], c["rate"])
        if key != cur:
            cur = key
            print(f"\n=== /{key[0]} @ {key[1]:,} rps " + "=" * 34)
            print(f"{'variant':15s} {'rep':>3s} {'err%':>7s} {'p50':>8s} {'p95':>8s} {'p99':>9s} "
                  f"{'p99.9':>9s} {'cores':>6s} {'heapMB':>7s} {'thr':>5s} {'hold':>7s} {'drop':>5s}")
        s = c.get("srv", {})
        flag = "  INVALID" if c["invalid"] else ""
        print(f"{c['variant']:15s} {c['rep']:>3d} {fmt((c['err_rate'] or 0) * 100, 2):>7s} "
              f"{fmt(c['p50']):>8s} {fmt(c['p95']):>8s} {fmt(c['p99']):>9s} {fmt(c['p999']):>9s} "
              f"{fmt(s.get('cores'), 3):>6s} {fmt(s.get('heap_mb'), 0):>7s} {fmt(s.get('threads_live'), 0):>5s} "
              f"{fmt(s.get('hold_ms'), 2):>7s} {fmt(c['dropped'], 0):>5s}{flag}")


if __name__ == "__main__":
    main()
