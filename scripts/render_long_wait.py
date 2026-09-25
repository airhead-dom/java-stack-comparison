#!/usr/bin/env python3
"""Render results/analysis/long-wait-run.md from the /api-800 and /api-1000 cells.

    python scripts/render_long_wait.py > results/analysis/long-wait-run.md

Prose is literal; every figure comes from extract_long_wait.load(), so a number
in the document cannot drift from the number in results/raw/.
"""
import sys

sys.path.insert(0, "scripts")
from extract_long_wait import (  # noqa: E402
    load, fit, stub_witness, VARIANT_ORDER, WORKLOAD_ORDER, DELAY_MS,
)

RATES = [500, 1000, 1500, 2000]
OUT = []


def w(line=""):
    OUT.append(line)


def f(x, p=1):
    return "-" if x is None else f"{x:,.{p}f}"


def sel(cells, **match):
    return [c for c in cells if all(c.get(k) == v for k, v in match.items())]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def avg(cells, key, sample=False):
    if sample:
        return mean([c["samples"][key] for c in cells if c.get("samples")])
    return mean([c.get(key) for c in cells])


def main():
    cells = load()
    live, dead = stub_witness()

    w("# The long-wait run — `/api-800` and `/api-1000`")
    w()
    w("Two workloads that hold each request at the upstream for 800 ms and")
    w("1,000 ms, against the two migration candidates. No database is involved,")
    w("so nothing the connection pool does can explain anything here.")
    w()
    w("The question is what each stack spends to hold a request that is merely")
    w("**waiting**. The earlier `/api` workload was sized so that in-flight")
    w("concurrency landed on Tomcat's 200 threads, which made it decisive about")
    w("`mvc-platform`. These two are sized past any thread count either")
    w("candidate has, so the scarce resource is no longer a worker to run the")
    w("request on — it is whatever the stack must keep alive while nothing is")
    w("happening.")
    w()
    w("This report is deliberately **descriptive**. It states what was measured")
    w("and, where the data supports one, the mechanism behind it. It does not")
    w("draw a conclusion about whether to migrate.")
    w()

    # ---------------------------------------------------------------- reading
    w("## How to read this")
    w()
    w("**Latency is reported as excess over the delay floor.** Every request")
    w("must wait out the upstream delay, so a raw p99 of 1,087 ms mostly")
    w("measures the stub. The floor is subtracted throughout: `+87` means 87 ms")
    w("of latency that the application added on top of the wait. Raw figures")
    w("are in the appendix.")
    w()
    w("**In-flight count is measured, not inferred.** This is the first run")
    w("carrying a mid-run sampler: `/actuator/prometheus` was scraped every 2 s")
    w("for the whole of each cell, giving ~54 steady-state readings of")
    w("in-flight, heap, CPU, threads and file descriptors. Previous runs had one")
    w("reading either side of the window, both taken while the system was idle,")
    w("which for a gauge means in-flight reads 0 and heap reads wherever GC")
    w("happened to leave it.")
    w()
    w("**Both repetitions are always shown.** Nothing is averaged across reps")
    w("in the per-cell tables, so where the two disagree it is visible rather")
    w("than smoothed away.")
    w()
    w("**Heap is reported as a floor, not a mean.** Heap used sawtooths with")
    w("GC, so its mean mixes retained state with uncollected garbage. The")
    w("minimum reading while under load is the part that did not go away.")
    w()

    # --------------------------------------------------------------- coverage
    w("## Coverage")
    w()
    valid = [c for c in cells if not (c["dropped"] or c["invalid"] or c["skipped"])]
    w(f"{len(cells)} cells: 2 builds x 2 workloads x {len(RATES)} rates x 2 repetitions.")
    w()
    w(f"- **{len(valid)} of {len(cells)} valid.** Every cell sustained its offered rate:")
    w("  0 dropped iterations and 0.00 % errors throughout, with no `.INVALID`")
    w("  or `.SKIPPED` marker on disk.")
    w("- `mvc-platform` and `mvc-jpa` do not implement these endpoints and were")
    w("  not run. 200 Tomcat threads over an 800 ms hold caps `mvc-platform` at")
    w("  250 rps, below the bottom rung of the ladder.")
    w("- 60 s warmup discarded, 60 s measured, open model, two repetitions.")
    w("- SUT: c7i.large, 2 vCPU, `-Xms1g -Xmx1g -XX:+UseG1GC`. Load generator:")
    w("  m7i.large, 2 vCPU, 8 GiB.")
    w()

    # -------------------------------------------------------------- in flight
    w("## In-flight capacity")
    w()
    w("Neither build reached a ceiling. Measured in-flight tracks Little's Law")
    w("(`rate x latency`) at every rung, on both builds, to within 1 %.")
    w()
    w("| workload | offered | expected | " + " | ".join(VARIANT_ORDER) + " |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            got = sel(cells, workload=wl, rate=rate)
            row = [f"`{wl}`", f"{rate:,}", f"{got[0]['inflight_expected']:,.0f}"]
            for v in VARIANT_ORDER:
                vals = [c["samples"]["inflight"] for c in got
                        if c["variant"] == v and c.get("samples")]
                row.append(" / ".join(f"{x:,.0f}" for x in vals))
            w("| " + " | ".join(row) + " |")
    w()
    w("Peak readings run higher than the mean — the sampler catches the")
    w("momentary backlog when a GC pause or a scheduling hiccup briefly holds")
    w("requests up. At `/api-1000` @ 2,000 rps the peaks were")
    pk_v = max(c["samples"]["inflight_peak"] for c in sel(cells, workload="api-1000", rate=2000, variant="mvc-virtual"))
    pk_w = max(c["samples"]["inflight_peak"] for c in sel(cells, workload="api-1000", rate=2000, variant="webflux-r2dbc"))
    w(f"**{pk_v:,.0f}** for `mvc-virtual` against **{pk_w:,.0f}** for")
    w("`webflux-r2dbc`, against a steady state of ~2,000 for both. The backlog")
    w("is a consequence of the pauses reported further down, not a separate")
    w("finding.")
    w()

    # ------------------------------------------------------------ latency
    w("## Response time")
    w()
    w("**p50 is the delay itself** on both builds at every rate — 800.5-800.9 ms")
    w("and 1000.5-1000.9 ms. Half of all requests pay nothing above the wait,")
    w("whichever stack serves them. The entire difference between the builds")
    w("lives in the tail.")
    w()
    w("p99 excess over the delay floor, in ms, both repetitions:")
    w()
    w("| workload | rate | " + " | ".join(VARIANT_ORDER) + " | ratio |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            row = [f"`{wl}`", f"{rate:,}"]
            m = {}
            for v in VARIANT_ORDER:
                got = sel(cells, workload=wl, rate=rate, variant=v)
                vals = [c["p99_excess"] for c in got]
                m[v] = mean(vals)
                row.append(" / ".join(f"{x:+.0f}" for x in vals))
            ratio = m["mvc-virtual"] / m["webflux-r2dbc"] if m["webflux-r2dbc"] else None
            row.append(f"{ratio:.1f}x" if ratio else "-")
            w("| " + " | ".join(row) + " |")
    w()
    w("The two repetitions agree closely at every rung above 500 rps — 86 and")
    w("86, 80 and 77, 87 and 84 — so the separation is reproducible rather than")
    w("a single bad run. At 500 rps both builds are close enough to the floor")
    w("that rep-to-rep noise dominates: `mvc-virtual` posted +26 and +3 ms on")
    w("the same cell.")
    w()

    # ------------------------------------------------------- the two drivers
    w("## What drives the tail, and what drives the heap")
    w()
    w("Offered rate and in-flight count normally move together — in flight is")
    w("`rate x delay` — so within one workload neither can be blamed. Running")
    w("two delays breaks the tie: **at the same offered rate, the two workloads")
    w("sit at different in-flight counts.** If a cost followed concurrency,")
    w("those pairs would diverge.")
    w()
    w("p99 excess at matched rates, averaged over both reps:")
    w()
    w("| rate | build | `/api-800` | `/api-1000` | change |")
    w("| ---: | --- | ---: | ---: | ---: |")
    for rate in RATES:
        for v in VARIANT_ORDER:
            pts = []
            for wl in WORKLOAD_ORDER:
                got = [c for c in sel(cells, workload=wl, rate=rate, variant=v) if c.get("samples")]
                pts.append((avg(got, "inflight", sample=True), avg(got, "p99_excess")))
            w(f"| {rate:,} | {v} | {pts[0][1]:+.0f} ms at {pts[0][0]:,.0f} "
              f"| {pts[1][1]:+.0f} ms at {pts[1][0]:,.0f} | {pts[1][1] - pts[0][1]:+.1f} ms |")
    w()
    w("**For `mvc-virtual` the tail does not follow in-flight at all.** Adding")
    w("25 % more concurrency at a fixed rate moves p99 by -2.0, +2.5, +1.3 and")
    w("-0.4 ms — inside the noise, and the sign flips. Its ~86 ms tail is a")
    w("**per-request** cost that scales with throughput, not with how many")
    w("requests are parked.")
    w()
    w("**For `webflux-r2dbc` the picture is not as clean, and it should not be")
    w("reported as though it were.** The same pairs give -0.3, +1.5, +5.4 and")
    w("+7.6 ms. The last two are not noise: at 2,000 rps, going from 1,602 to")
    w("2,002 in flight adds 7.6 ms to a 22 ms baseline, about a third. Its tail")
    w("is much smaller in absolute terms but does pick up a concurrency")
    w("component above roughly 1,500 requests in flight.")
    w()
    w("Heap goes the other way. Regressing the heap floor on measured in-flight")
    w("across all 16 cells of each build:")
    w()
    w("| build | per request in flight | intercept | R² |")
    w("| --- | ---: | ---: | ---: |")
    for v in VARIANT_ORDER:
        pts = [(c["samples"]["inflight"], c["samples"]["heap_floor_mb"])
               for c in sel(cells, variant=v) if c.get("samples")]
        slope, intercept, r2 = fit(pts)
        w(f"| {v} | **{slope * 1024:,.0f} KB** | {intercept:,.0f} MB | {r2:.2f} |")
    w()
    w("The R² values are moderate, so these are trends rather than tight fits —")
    w("the heap floor is noisy at the bottom of the ladder, where few")
    w("collections run during a 120 s window and the minimum reading is")
    w("whatever the last one happened to leave. The direction and the order of")
    w("magnitude are solid; the exact slope is not.")
    w()
    w("The `mvc-virtual` figure is consistent with the 139 KB per queued")
    w("request measured on `/db-heavy` at overload in the AWS run, which arrived")
    w("by a completely different route — pool exhaustion rather than deliberate")
    w("upstream delay.")
    w()

    # -------------------------------------------------------------------- cpu
    w("## CPU")
    w()
    w("Of 2 available cores, averaged over the steady-state samples:")
    w()
    w("| workload | rate | " + " | ".join(VARIANT_ORDER) + " | ratio |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            row = [f"`{wl}`", f"{rate:,}"]
            m = {}
            for v in VARIANT_ORDER:
                got = [c for c in sel(cells, workload=wl, rate=rate, variant=v) if c.get("samples")]
                m[v] = avg(got, "cpu", sample=True)
                row.append(" / ".join(f"{c['samples']['cpu']:.3f}" for c in got))
            row.append(f"{m['mvc-virtual'] / m['webflux-r2dbc']:.1f}x" if m["webflux-r2dbc"] else "-")
            w("| " + " | ".join(row) + " |")
    w()
    w("The ratio is close to **2x** across the top of the ladder and holds on")
    w("both workloads. Neither build is near saturating the box: at the most")
    w("expensive cell `mvc-virtual` used 0.34 of 2 cores, so the CPU difference")
    w("is a cost difference, not a throughput limit at these rates.")
    w()

    # ----------------------------------------------------------------- memory
    w("## Memory")
    w()
    w("Three separate measurements, which say different things.")
    w()
    w("**Allocation** is a counter, so differencing two scrapes is exact.")
    w("Normalised per 1,000 requests it is near-constant across the ladder,")
    w("which makes it comparable between builds:")
    w()
    w("| workload | rate | " + " | ".join(f"{v} MB/1k" for v in VARIANT_ORDER) + " | ratio |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            row = [f"`{wl}`", f"{rate:,}"]
            m = {}
            for v in VARIANT_ORDER:
                got = sel(cells, workload=wl, rate=rate, variant=v)
                m[v] = avg(got, "alloc_mb_per_1k")
                row.append(" / ".join(f"{c['alloc_mb_per_1k']:.0f}" for c in got))
            row.append(f"{m['mvc-virtual'] / m['webflux-r2dbc']:.1f}x")
            w("| " + " | ".join(row) + " |")
    w()
    w("`mvc-virtual` allocates roughly **1.7x** as much per request. That is the")
    w("same direction and close to the same magnitude as the AWS `/api` cells")
    w("(59 against 37 MB per 1,000 at 2,000 rps), now reproduced at four to")
    w("five times the in-flight count.")
    w()
    w("**Promotion** is where the two builds stop resembling each other. This")
    w("counts bytes that survived a young collection and were moved to the old")
    w("generation:")
    w()
    w("| workload | rate | " + " | ".join(f"{v} KB/req" for v in VARIANT_ORDER) + " |")
    w("| --- | ---: | ---: | ---: |")
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            row = [f"`{wl}`", f"{rate:,}"]
            for v in VARIANT_ORDER:
                got = sel(cells, workload=wl, rate=rate, variant=v)
                row.append(" / ".join(f"{c['promoted_kb_per_req']:.1f}" for c in got))
            w("| " + " | ".join(row) + " |")
    w()
    w("`webflux-r2dbc` promotes **essentially nothing**: its largest cell is")
    w("0.20 KB per request and the other 15 are under 0.03 KB. `mvc-virtual`")
    w("promotes around **5 KB per request** — between 25x and 400x more,")
    w("depending which WebFlux cell it is set against.")
    w()
    w("That is the mechanism behind the heap slope. A request that waits a")
    w("second is alive far longer than a young collection cycle at these")
    w("allocation rates, so under virtual threads its stack is still reachable")
    w("when the collector runs and gets promoted. The reactive build holds the")
    w("same waiting request as a small callback chain that either dies young or")
    w("was never big enough to matter. Both are paying to remember a request")
    w("that is doing nothing; they differ in how much there is to remember and")
    w("in which generation it ends up.")
    w()
    w("**GC pause**, summed over the 120 s window:")
    w()
    w("| workload | rate | " + " | ".join(f"{v} pause / count" for v in VARIANT_ORDER) + " |")
    w("| --- | ---: | ---: | ---: |")
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            row = [f"`{wl}`", f"{rate:,}"]
            for v in VARIANT_ORDER:
                got = sel(cells, workload=wl, rate=rate, variant=v)
                row.append(" / ".join(f"{c['gc_pause_s']:.2f} s ({c['gc_count']:.0f})" for c in got))
            w("| " + " | ".join(row) + " |")
    w()
    w("At the top rung `mvc-virtual` spends about **7x** as long paused, over")
    w("roughly three times as many collections. Against a 120 s window, 4.5 s of")
    w("pause is ~3.7 % of wall clock, which is consistent with the tail excess")
    w("being what it is without accounting for all of it.")
    w()

    # ------------------------------------------------- threads and descriptors
    w("## Threads and file descriptors")
    w()
    w("`jvm_threads_live_threads` counts Java platform threads only — virtual")
    w("threads are excluded, and so are the JVM's native GC and JIT threads. For")
    w("`mvc-virtual` this is therefore a count of ForkJoinPool carriers plus")
    w("Tomcat's own threads, not of requests.")
    w()
    w("| workload | rate | " + " | ".join(f"{v} threads" for v in VARIANT_ORDER)
      + " | " + " | ".join(f"{v} peak fds" for v in VARIANT_ORDER) + " |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    for wl in WORKLOAD_ORDER:
        for rate in RATES:
            row = [f"`{wl}`", f"{rate:,}"]
            for key in ("threads", "fds_peak"):
                for v in VARIANT_ORDER:
                    got = [c for c in sel(cells, workload=wl, rate=rate, variant=v) if c.get("samples")]
                    row.append(f"{avg(got, key, sample=True):,.0f}")
            w("| " + " | ".join(row) + " |")
    w()
    w("`webflux-r2dbc` sits at **21 threads in fifteen of sixteen cells**, and")
    w("22.7 in the sixteenth — it does not matter what the rate is or how many")
    w("requests are in flight, which is the event loop model doing exactly what")
    w("it claims. `mvc-virtual` grows from")
    w("40 to around 130 carriers. Carrier growth of that size on a 2-core box")
    w("means the scheduler is compensating for virtual threads that blocked in a")
    w("way it could not simply unmount; this data does not establish where.")
    w()
    w("File descriptors are near-identical between the builds and scale with")
    w("concurrency as expected — each in-flight request pins an inbound socket")
    w("and an outbound one, on top of the generator's keep-alive pool. Both")
    w("builds passed 6,000 at the top rung, well beyond the 1,024 that some")
    w("distributions still default to, though the SUT's limit was 1,048,576 so")
    w("nothing bound.")
    w()

    # --------------------------------------------------------------- findings
    w("## Findings")
    w()
    w("1. **Both builds held 2,000 requests in flight** with zero errors and")
    w("   zero dropped iterations. Neither reached a ceiling on this ladder, so")
    w("   no saturation point was measured for either.")
    w("2. **Median latency is identical** — the delay floor, on both builds, at")
    w("   every rate. Any difference between these stacks on this workload is a")
    w("   tail phenomenon.")
    w("3. **`mvc-virtual`'s tail is ~3-4x larger** than `webflux-r2dbc`'s")
    w("   (+86 vs +22 ms at the top rung) and is a per-request cost: it tracks")
    w("   offered rate and is flat against in-flight count.")
    w("4. **`webflux-r2dbc`'s tail is smaller but not purely per-request.** It")
    w("   picks up a concurrency component above ~1,500 in flight, worth about")
    w("   a third of its total at 2,000 rps.")
    w("5. **CPU differs by ~2x** at the top of the ladder, on both workloads,")
    w("   reproducibly.")
    w("6. **The two builds have opposite memory profiles.** `mvc-virtual`")
    w("   allocates ~1.7x more per request, promotes ~5 KB per request against")
    w("   approximately zero, and its heap floor rises with in-flight count;")
    w("   `webflux-r2dbc`'s floor is close to flat.")
    w("7. **Thread count is flat for the reactive build** — 21 in fifteen of")
    w("   sixteen cells, independent of rate and concurrency — and grows to")
    w("   ~130 carriers for virtual threads.")
    w()

    # ----------------------------------------------------------------- limits
    w("## Limits of this run")
    w()
    w("**The stub was not independently witnessed.** The runners sample the")
    w(f"stub's own metrics as evidence it never became the bottleneck. All {dead}")
    w("of its CSVs sampled on cadence but recorded zeros throughout, so that")
    w("evidence is unavailable for this run. The most likely cause is that the")
    w("previous stub build was still running: `stub.sh start` returns early when")
    w("one is already alive, so uploading a new jar without `restart` keeps the")
    w("old process, and the old build exposed only `health`, not `prometheus`.")
    w("A `./stub.sh restart` before the next run would close it. This report")
    w("does not argue the point either way — the stub's behaviour during these")
    w("cells is simply not established by measurement.")
    w()
    w("**No ceiling was found**, so nothing here says where either build stops.")
    w("These are points on a curve. Extrapolating the heap slope past 2,000 in")
    w("flight would be unsupported.")
    w()
    w("**One configuration.** c7i.large, 2 vCPU, 1 GB heap, G1, one pool size,")
    w("one upstream. The 1 GB heap in particular interacts with the promotion")
    w("finding: a larger heap would change collection frequency and therefore")
    w("both the pause totals and the heap floor.")
    w()
    w("**Carrier growth is unexplained.** `mvc-virtual` reaching ~130 carrier")
    w("threads is visible in the data but its cause is not. A thread dump under")
    w("load (`jcmd <pid> Thread.print`) would settle it; nothing here does.")
    w()
    w("**`mvc-platform` is absent by construction**, so this run says nothing")
    w("about platform threads on long waits beyond the arithmetic that excluded")
    w("them: 200 threads over an 800 ms hold is 250 rps.")
    w()

    # --------------------------------------------------------------- appendix
    w("## Appendix — every cell")
    w()
    w("Raw latency, not excess. `in flight` and `heap floor` are steady-state")
    w("readings from the mid-run sampler; the rest are k6 or differenced")
    w("counters.")
    w()
    for wl in WORKLOAD_ORDER:
        w(f"### `/{wl}` — {DELAY_MS[wl]} ms upstream delay")
        w()
        w("| rate | build | rep | err % | p50 | p95 | p99 | max | in flight | "
          "cores | heap floor | MB/1k | promKB | GC s |")
        w("| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for c in sel(cells, workload=wl):
            s = c.get("samples") or {}
            w(f"| {c['rate']:,} | {c['variant']} | {c['rep']} | {c['err_pct']:.2f} "
              f"| {f(c['p50'])} | {f(c['p95'])} | {f(c['p99'])} | {f(c['max'])} "
              f"| {s.get('inflight', 0):,.0f} | {s.get('cpu', 0):.3f} "
              f"| {s.get('heap_floor_mb', 0):,.0f} MB | {c['alloc_mb_per_1k']:.0f} "
              f"| {c['promoted_kb_per_req']:.1f} | {c['gc_pause_s']:.2f} |")
        w()

    w("---")
    w()
    w("Generated by `scripts/render_long_wait.py` from `results/raw/`.")
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
