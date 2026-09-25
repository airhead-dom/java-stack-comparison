#!/usr/bin/env python3
"""Pull the /api-800 and /api-1000 cells into one structured dataset.

    python scripts/extract_long_wait.py            # summary tables to stdout
    python scripts/extract_long_wait.py --json     # the raw dataset

These two workloads are the first to carry a mid-run sampler, so each cell has
three sources rather than two:

  *.json                      k6, client side: latency, errors, dropped iterations
  *.metrics.before/after.txt  counters differenced across the measured window
  *.samples.csv               ~61 gauge readings taken DURING the run

The third is why this is a separate loader from extract_results.py. A gauge read
either side of the window is read while the system is idle: in-flight reads 0
and heap reads wherever GC happened to leave it. In-flight count is the whole
question for these workloads, so it has to be sampled while load is on.
"""
import csv
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Prometheus parsing is already solved next door, including the awkward part:
# the value is the LAST field, because label values may contain spaces.
from extract_results import parse_prom, total, delta  # noqa: E402

RAW = "results/raw"
CELL = re.compile(r"(.+?)__(api-\d+)__(\d+)rps__r(\d+)$")
VARIANT_ORDER = ["webflux-r2dbc", "mvc-virtual"]
WORKLOAD_ORDER = ["api-800", "api-1000"]
# The upstream delay each workload asks the stub for. Latency is reported as
# excess over this floor: every request must wait it out, so the floor is not a
# property of either build and quoting raw p99 hides the part that is.
DELAY_MS = {"api-800": 800, "api-1000": 1000}
# Samples with nothing in flight are warmup head and drain tail. Three more are
# dropped at each end because the first and last loaded samples straddle the
# ramp, and a half-loaded sample would drag the steady-state mean.
TRIM = 3


def k6(path):
    """Client-side truth: what the generator actually saw."""
    m = json.load(open(path, encoding="utf-8"))["metrics"]

    def v(name, key):
        return m.get(name, {}).get("values", {}).get(key)

    return {
        "reqs": v("http_reqs{phase:measure}", "count"),
        "dropped": v("dropped_iterations{scenario:measure}", "count") or 0,
        "err_pct": (v("http_req_failed{phase:measure}", "rate") or 0) * 100,
        "p50": v("http_req_duration{phase:measure}", "p(50)"),
        "p95": v("http_req_duration{phase:measure}", "p(95)"),
        "p99": v("http_req_duration{phase:measure}", "p(99)"),
        "max": v("http_req_duration{phase:measure}", "max"),
    }


def samples(path):
    """Steady-state summary of the mid-run gauge series."""
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8"))
            if r.get("in_flight") and int(r["in_flight"]) > 0]
    rows = rows[TRIM:-TRIM] if len(rows) > 2 * TRIM else rows
    if not rows:
        return None

    def col(key):
        return [float(r[key]) for r in rows]

    inflight, heap, cpu = col("in_flight"), col("heap_used_b"), col("cpu")
    threads, fds = col("threads_live"), col("files_open")

    def mean(xs):
        return sum(xs) / len(xs)

    return {
        "n": len(rows),
        "inflight": mean(inflight),
        "inflight_peak": max(inflight),
        "heap_mb": mean(heap) / 2**20,
        "heap_max_mb": max(heap) / 2**20,
        # The post-collection floor, not the mean. Heap used sawtooths, so its
        # mean mixes retained state with uncollected garbage; the floor is the
        # part that did not go away, which is what scales with in-flight.
        "heap_floor_mb": min(heap) / 2**20,
        "cpu": mean(cpu),
        "threads": mean(threads),
        "threads_peak": max(threads),
        "fds_peak": max(fds),
    }


def counters(before, after, workload):
    """Counters differenced across the window. The JVM stays up across a whole
    ladder, so a raw reading is a since-startup total covering other cells."""
    b, a = parse_prom(before), parse_prom(after)

    def d(name, **match):
        return delta(b, a, name, **match)

    reqs = d("http_server_requests_seconds_count", uri="/" + workload)
    alloc = d("jvm_gc_memory_allocated_bytes_total")
    promoted = d("jvm_gc_memory_promoted_bytes_total")
    return {
        "srv_reqs": reqs,
        "alloc_gb": (alloc or 0) / 2**30,
        # Normalised so cells at different rates are comparable at all.
        "alloc_mb_per_1k": (alloc / 2**20) / (reqs / 1000) if alloc and reqs else None,
        "promoted_mb": (promoted or 0) / 2**20,
        # Promotion is what separates a request that outlives the young
        # generation from one that does not.
        "promoted_kb_per_req": (promoted / 1024) / reqs if promoted and reqs else 0.0,
        "gc_pause_s": d("jvm_gc_pause_seconds_sum") or 0.0,
        "gc_count": d("jvm_gc_pause_seconds_count") or 0.0,
        "cores": total(a, "system_cpu_count"),
    }


def load():
    cells = []
    for path in sorted(glob.glob(os.path.join(RAW, "*__api-*rps__r*.json"))):
        tag = os.path.basename(path)[:-len(".json")]
        m = CELL.match(tag)
        if not m:
            continue
        variant, workload, rate, rep = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))

        before = os.path.join(RAW, tag + ".metrics.before.txt")
        after = os.path.join(RAW, tag + ".metrics.after.txt")
        scsv = os.path.join(RAW, tag + ".samples.csv")
        missing = [os.path.basename(p) for p in (before, after, scsv) if not os.path.exists(p)]

        cell = {
            "tag": tag, "variant": variant, "workload": workload,
            "rate": rate, "rep": rep, "delay_ms": DELAY_MS[workload],
            "missing": missing,
            # A cell that could not sustain its offered rate is not an
            # open-model measurement; the runners mark it on disk.
            "invalid": os.path.exists(os.path.join(RAW, tag + ".INVALID")),
            "skipped": os.path.exists(os.path.join(RAW, tag + ".SKIPPED")),
        }
        cell.update(k6(path))
        if not missing:
            cell.update(counters(before, after, workload))
            cell["samples"] = samples(scsv)
        # Expected in flight by Little's Law, for comparison with measured.
        cell["inflight_expected"] = rate * (DELAY_MS[workload] / 1000.0)
        # Latency above the floor every request must wait out regardless.
        for k in ("p50", "p95", "p99"):
            cell[k + "_excess"] = (cell[k] - cell["delay_ms"]) if cell[k] is not None else None
        cells.append(cell)

    cells.sort(key=lambda c: (WORKLOAD_ORDER.index(c["workload"]),
                              c["rate"],
                              VARIANT_ORDER.index(c["variant"]) if c["variant"] in VARIANT_ORDER else 9,
                              c["rep"]))
    return cells


def stub_witness():
    """Did the stub's own metrics come back at all? The runners sample it as a
    witness that it was never the bottleneck; an empty series means that
    evidence is unavailable for the run, not that the stub was idle."""
    live = dead = 0
    for path in glob.glob(os.path.join(RAW, "*__api-*rps__r*.stub.csv")):
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        if any(float(r.get("heap_used_b") or 0) > 0 for r in rows):
            live += 1
        else:
            dead += 1
    return live, dead


def fit(points):
    """Least squares through (x, y), returning slope, intercept and R^2.

    A two-point slope between the lowest and highest cell would let one noisy
    endpoint set the headline figure, and the heap floor is noisy at the bottom
    of the ladder where few collections run. R^2 is reported so a slope quoted
    from a scattered fit cannot be mistaken for a tight one.
    """
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    sxy = sum((x - mx) * (y - my) for x, y in points)
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    sst = sum((y - my) ** 2 for _, y in points)
    ssr = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
    return slope, intercept, (1 - ssr / sst) if sst else 0.0


def fmt(x, nd=1):
    return "-" if x is None else f"{x:,.{nd}f}"


def by(cells, **match):
    return [c for c in cells if all(c[k] == v for k, v in match.items())]


def main():
    cells = load()
    if "--json" in sys.argv:
        json.dump(cells, sys.stdout, indent=2, default=str)
        return

    bad = [c for c in cells if c["missing"]]
    print(f"{len(cells)} cells loaded"
          + (f", {len(bad)} with missing files" if bad else ", all sources present"))
    for c in bad:
        print(f"  {c['tag']}: missing {', '.join(c['missing'])}")

    dropped = [c for c in cells if c["dropped"] or c["invalid"] or c["skipped"]]
    print("validity: " + ("all cells sustained their offered rate"
                          if not dropped else f"{len(dropped)} cells NOT valid"))
    for c in dropped:
        print(f"  {c['tag']}: dropped={c['dropped']:.0f} invalid={c['invalid']} skipped={c['skipped']}")

    live, dead = stub_witness()
    print(f"stub witness: {live} cells with data, {dead} empty")

    print("\n=== IN-FLIGHT CAPACITY (steady state, measured on the server) ===")
    print(f"{'workload':10}{'rate':>6}{'expected':>10}", end="")
    for v in VARIANT_ORDER:
        print(f"{v:>18}", end="")
    print()
    for w in WORKLOAD_ORDER:
        for rate in sorted({c["rate"] for c in by(cells, workload=w)}):
            got = by(cells, workload=w, rate=rate)
            print(f"{w:10}{rate:>6}{got[0]['inflight_expected']:>10,.0f}", end="")
            for v in VARIANT_ORDER:
                s = [c["samples"] for c in got if c["variant"] == v and c.get("samples")]
                print(f"{'  '.join(f'{x['inflight']:,.0f}' for x in s):>18}", end="")
            print()

    print("\n=== RESPONSE TIME (ms; excess over the delay floor in brackets) ===")
    print(f"{'workload':10}{'rate':>6}{'variant':>15}{'r':>3}"
          f"{'p50':>10}{'p95':>10}{'p99':>16}{'max':>9}{'err%':>7}")
    for c in cells:
        p99 = f"{c['p99']:,.1f} ({c['p99_excess']:+.0f})"
        print(f"{c['workload']:10}{c['rate']:>6}{c['variant']:>15}{c['rep']:>3}"
              f"{fmt(c['p50']):>10}{fmt(c['p95']):>10}{p99:>16}{fmt(c['max']):>9}"
              f"{c['err_pct']:>7.2f}")

    print("\n=== RESOURCE USE (steady state; counters differenced) ===")
    print(f"{'workload':10}{'rate':>6}{'variant':>15}{'r':>3}"
          f"{'cores':>7}{'heapAvg':>9}{'heapFloor':>11}{'MB/1k':>8}"
          f"{'promKB/req':>12}{'gc_s':>7}{'gcs':>5}{'thr':>6}{'fds':>7}")
    for c in cells:
        s = c.get("samples") or {}
        print(f"{c['workload']:10}{c['rate']:>6}{c['variant']:>15}{c['rep']:>3}"
              f"{s.get('cpu', 0):>7.3f}{s.get('heap_mb', 0):>9.0f}{s.get('heap_floor_mb', 0):>11.0f}"
              f"{c.get('alloc_mb_per_1k') or 0:>8.1f}{c.get('promoted_kb_per_req') or 0:>12.1f}"
              f"{c.get('gc_pause_s') or 0:>7.2f}{c.get('gc_count') or 0:>5.0f}"
              f"{s.get('threads', 0):>6.0f}{s.get('fds_peak', 0):>7.0f}")

    print("\n=== THE TWO DRIVERS ===")
    print("tail excess by offered rate, averaged over reps and both workloads:")
    for v in VARIANT_ORDER:
        line = []
        for rate in (500, 1000, 1500, 2000):
            got = [c["p99_excess"] for c in by(cells, variant=v, rate=rate)]
            line.append(f"{rate}:{sum(got)/len(got):5.1f}ms")
        print(f"  {v:15} " + "  ".join(line))
    # The decisive comparison. Rate and in-flight are normally locked together
    # (in flight = rate x delay), so neither can be blamed from one workload
    # alone. Two delays break the tie: at the SAME offered rate the two
    # workloads sit at different in-flight counts. If the tail followed
    # in-flight these pairs would diverge; if it follows rate they will match.
    print("\nsame rate, different in-flight -- does the tail follow either?")
    print(f"  {'rate':>6}{'variant':>15}{'/api-800':>22}{'/api-1000':>22}{'delta':>8}")
    for rate in (500, 1000, 1500, 2000):
        for v in VARIANT_ORDER:
            row = []
            for w in WORKLOAD_ORDER:
                got = [c for c in by(cells, variant=v, rate=rate, workload=w) if c.get("samples")]
                inf = sum(c["samples"]["inflight"] for c in got) / len(got)
                exc = sum(c["p99_excess"] for c in got) / len(got)
                row.append((inf, exc))
            d = row[1][1] - row[0][1]
            print(f"  {rate:>6}{v:>15}"
                  f"{f'{row[0][1]:.0f}ms at {row[0][0]:,.0f}':>22}"
                  f"{f'{row[1][1]:.0f}ms at {row[1][0]:,.0f}':>22}{d:>+8.1f}")

    print("\nheap floor against measured in-flight, least squares over all 16 cells:")
    for v in VARIANT_ORDER:
        pts = [(c["samples"]["inflight"], c["samples"]["heap_floor_mb"])
               for c in by(cells, variant=v) if c.get("samples")]
        slope, intercept, r2 = fit(pts)
        print(f"  {v:15} {slope * 1024:>6,.0f} KB per request in flight"
              f"   (intercept {intercept:,.0f}MB, R^2 {r2:.2f}, n={len(pts)})")


if __name__ == "__main__":
    main()
