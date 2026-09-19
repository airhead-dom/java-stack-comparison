#!/usr/bin/env python3
"""Turn results/raw/ into comparison tables.

    python scripts/summarize.py                 # everything found
    python scripts/summarize.py api             # one workload
    python scripts/summarize.py > report.md     # markdown tables

Reads the k6 JSON for latency and the before/after Prometheus scrapes for
CPU, memory and threads. Cells with a .INVALID marker are listed separately
and excluded from the tables - k6 failed to offer the target rate in those,
so they understate the load.
"""
import glob
import json
import os
import re
import statistics as st
import sys

RAW = "results/raw"
VARIANT_ORDER = ["mvc-platform", "mvc-virtual", "webflux-r2dbc", "mvc-jpa"]


def metric(text, name, where=None):
    """Sum a Prometheus metric. The value is the last field because label
    values can contain spaces (e.g. id="G1 Eden Space")."""
    total, found = 0.0, False
    for line in text.splitlines():
        if not line.startswith(name):
            continue
        if where and where not in line:
            continue
        try:
            total += float(line.rsplit(None, 1)[1])
            found = True
        except (ValueError, IndexError):
            pass
    return total if found else None


def read_cell(path):
    base = os.path.basename(path)[: -len(".json")]
    m = re.match(r"(.+?)__(.+?)__(\d+)rps__r(\d+)$", base)
    if not m:
        return None
    variant, workload, rate, rep = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))

    with open(path) as fh:
        metrics = json.load(fh)["metrics"]

    def val(key, field, default=0.0):
        return metrics.get(key, {}).get("values", {}).get(field, default)

    dur = metrics.get("http_req_duration{phase:measure}", {}).get("values", {})
    cell = {
        "variant": variant, "workload": workload, "rate": rate, "rep": rep,
        "rps": val("http_reqs", "rate"),
        "err": val("http_req_failed{phase:measure}", "rate") * 100,
        "p50": dur.get("p(50)"), "p95": dur.get("p(95)"),
        "p99": dur.get("p(99)"), "max": dur.get("max"),
        "dropped": val("dropped_iterations{scenario:measure}", "count"),
        "invalid": os.path.exists(os.path.join(RAW, base + ".INVALID")),
    }

    before = os.path.join(RAW, base + ".metrics.before.txt")
    after = os.path.join(RAW, base + ".metrics.after.txt")
    if os.path.exists(before) and os.path.exists(after):
        b = open(before, encoding="utf-8", errors="ignore").read()
        a = open(after, encoding="utf-8", errors="ignore").read()
        cell["heap"] = (metric(a, "jvm_memory_used_bytes", 'area="heap"') or 0) / 2**20
        cell["threads"] = metric(a, "jvm_threads_live_threads")
        cell["pool_pending"] = (metric(a, "hikaricp_connections_pending")
                                or metric(a, "r2dbc_pool_pending_connections"))
        # Connection hold time, differenced so it describes this run rather
        # than everything since the JVM started.
        for key, dest in (("hikaricp_connections_usage_seconds", "hold_ms"),):
            s0, c0 = metric(b, key + "_sum"), metric(b, key + "_count")
            s1, c1 = metric(a, key + "_sum"), metric(a, key + "_count")
            if None not in (s0, c0, s1, c1) and (c1 - c0) > 0:
                cell[dest] = (s1 - s0) / (c1 - c0) * 1000
        gc0, gc1 = metric(b, "jvm_gc_pause_seconds_sum"), metric(a, "jvm_gc_pause_seconds_sum")
        if None not in (gc0, gc1):
            cell["gc_ms"] = (gc1 - gc0) * 1000
    return cell


def fmt(x, places=1):
    return "-" if x is None else f"{x:.{places}f}"


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    cells = [c for c in (read_cell(p) for p in sorted(glob.glob(f"{RAW}/*__*rps__r*.json"))) if c]
    if not cells:
        print(f"no results found in {RAW}/")
        return
    if only:
        cells = [c for c in cells if c["workload"] == only]

    valid = [c for c in cells if not c["invalid"]]
    invalid = [c for c in cells if c["invalid"]]

    groups = {}
    for c in valid:
        groups.setdefault((c["workload"], c["rate"]), {}).setdefault(c["variant"], []).append(c)

    print(f"# Benchmark results\n\n{len(valid)} valid cells, {len(invalid)} invalid.")
    print("\nLatency values are milliseconds. Medians across repetitions; "
          "per-run p99 shown so the spread is visible.\n")

    for (workload, rate) in sorted(groups, key=lambda k: (k[0], k[1])):
        print(f"\n## `/{workload}` @ {rate} rps\n")
        print("| variant | runs | rps | err % | p50 | p95 | p99 | max | p99 per run |")
        print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
        by_variant = groups[(workload, rate)]
        for v in [x for x in VARIANT_ORDER if x in by_variant] + \
                 [x for x in by_variant if x not in VARIANT_ORDER]:
            runs = by_variant[v]
            med = lambda k: st.median([r[k] for r in runs if r[k] is not None]) \
                if any(r[k] is not None for r in runs) else None
            spread = " / ".join(fmt(r["p99"]) for r in sorted(runs, key=lambda r: r["rep"]))
            print(f"| {v} | {len(runs)} | {fmt(med('rps'), 0)} | {fmt(med('err'), 2)} | "
                  f"{fmt(med('p50'))} | {fmt(med('p95'))} | {fmt(med('p99'))} | "
                  f"{fmt(med('max'))} | {spread} |")

        if any("heap" in r for runs in by_variant.values() for r in runs):
            print(f"\n**Server side**\n")
            print("| variant | heap MB | threads | pool pending | hold ms | GC ms |")
            print("| --- | ---: | ---: | ---: | ---: | ---: |")
            for v in [x for x in VARIANT_ORDER if x in by_variant]:
                runs = by_variant[v]
                med = lambda k: st.median([r[k] for r in runs if r.get(k) is not None]) \
                    if any(r.get(k) is not None for r in runs) else None
                print(f"| {v} | {fmt(med('heap'), 0)} | {fmt(med('threads'), 0)} | "
                      f"{fmt(med('pool_pending'), 0)} | {fmt(med('hold_ms'), 2)} | "
                      f"{fmt(med('gc_ms'), 0)} |")

    if invalid:
        print("\n## Excluded\n")
        print("k6 dropped iterations during the measured phase, so the offered rate "
              "was not sustained. These understate the load and must not be plotted.\n")
        for c in sorted(invalid, key=lambda c: (c["workload"], c["rate"], c["variant"])):
            print(f"- `{c['variant']}` {c['workload']} @ {c['rate']} rps "
                  f"run {c['rep']} - {int(c['dropped'])} dropped")


if __name__ == "__main__":
    main()
