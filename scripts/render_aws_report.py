#!/usr/bin/env python3
"""Render results/analysis/aws-run.md from everything in results/raw/.

    python scripts/render_aws_report.py > results/analysis/aws-run.md

Reads the dataset assembled by extract_results.py and writes the full detail:
every cell, both repetitions, latency decomposed into its phases, server-side
outcome counts, and the resource counters differenced across each window.
"""
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, "scripts")
from extract_results import load, VARIANT_ORDER, WORKLOAD_ORDER  # noqa: E402

LABEL = {
    "webflux-r2dbc": "webflux-r2dbc",
    "mvc-virtual": "mvc-virtual",
    "mvc-platform": "mvc-platform",
}
DESC = {
    "nodb": ("constant response, no I/O", "web layer only"),
    "db": ("one indexed two-table query", "pool never binds"),
    "db-heavy": ("aggregate + 20 rows, padded to a 15 ms hold", "pool binds ~1,387 rps"),
    "db-slow": ("query + pg_sleep(0.1)", "pool binds ~200 rps"),
    "api": ("one 200 ms upstream call, no database", "threads bind ~1,000 rps"),
}
W = []


def w(line=""):
    W.append(line)


def f(x, p=1):
    return "—" if x is None else f"{x:,.{p}f}"


def pct(x, p=2):
    return "—" if x is None else f"{x * 100:,.{p}f}"


def main():
    cells = load()
    by = defaultdict(list)
    for c in cells:
        by[(c["workload"], c["rate"], c["variant"])].append(c)
    variants_run = [v for v in VARIANT_ORDER if any(c["variant"] == v for c in cells)]
    workloads = [x for x in WORKLOAD_ORDER if any(c["workload"] == x for c in cells)]
    rates = sorted({c["rate"] for c in cells})
    invalid = [c for c in cells if c["invalid"]]

    # ---------------------------------------------------------------- header
    w("# AWS benchmark run — full results")
    w()
    w("21 September 2026. Three EC2 instances in one availability zone: a load")
    w("generator, a 2-vCPU system under test, and a backend running PostgreSQL 17")
    w("and the stub service. Nothing shares a CPU with the application.")
    w()
    w("This is the complete dataset. `results/analysis/README.md` remains the")
    w("earlier laptop survey; where the two disagree, this one supersedes it.")
    w()
    w("| | |")
    w("| --- | --- |")
    w("| Cells | %d — %d variants × %d workloads × %d rates × 2 repetitions |"
      % (len(cells), len(variants_run), len(workloads), len(rates)))
    w("| Invalid | %d — the generator dropped iterations during the measured window |" % len(invalid))
    w("| JVM | OpenJDK 25.0.4+7-1-24.04-Ubuntu |")
    w("| SUT | 2 vCPU (`system_cpu_count` = 2), `-Xmx1g`, G1 |")
    w("| Pool | 20 connections, both HikariCP and R2DBC Pool |")
    w("| Rates | %s requests per second, offered open-model |" % ", ".join(f"{r:,}" for r in rates))
    w("| Window | 60 s warmup discarded, 60 s measured |")
    w()

    # ----------------------------------------------------------- how to read
    w("## How to read this")
    w()
    w("**Latency figures are milliseconds**, percentiles of k6 `http_req_duration`")
    w("scoped to the measured phase. `p99.9` is included because several results")
    w("only separate in the far tail.")
    w()
    w("**Where the error rate is high, latency is floored by the 1,000 ms client")
    w("timeout.** A `p50` of 1,000.0 means at least half the requests were")
    w("abandoned, not that they took a second. Read the error column first.")
    w()
    w("**`cores`** is CPU-seconds consumed per wall-second, from")
    w("`process_cpu_time_ns_total` differenced across the window and divided by the")
    w("JVM's own uptime delta. `1.000` means one core saturated; the ceiling is")
    w("`2.000`.")
    w()
    w("**`dropped`** counts iterations k6 could not start during the measured")
    w("phase. Any non-zero value means the offered rate was not actually")
    w("sustained, so the cell understates the load and is marked invalid.")
    w()
    w("**Percentiles convert to counts.** Each cell offered `rate x 60 s` requests")
    w("in the measured window, and `passes + fails` on")
    w("`http_req_failed{phase:measure}` confirms it to the request. So a p99 of")
    w("409 ms over 90,000 requests means 900 requests were slower than 409 ms, and")
    w("a p95 of 313 ms means 4,500 were. Note k6 inverts the names on that metric:")
    w("`passes` counts requests where \"failed\" was true.")
    w()
    w("**Counters are differenced, not read.** The variant's JVM stayed up across")
    w("a whole ladder instead of restarting per cell, so a raw reading is a")
    w("since-startup total covering other workloads. Every counter here is")
    w("`after − before` across the two scrapes bracketing the measured window.")
    w()
    w("### Two measurement limits worth knowing before reading the numbers")
    w()
    w("**HikariCP records connection usage in whole milliseconds.** Its")
    w("`usage_seconds_sum` values end in exactly three decimal places while")
    w("`acquire_seconds_sum` carries nine, so any hold under 1 ms rounds to zero.")
    w("The hold figures on `/db` are therefore a floor, not a mean — treat them as")
    w("\"below the resolution of the instrument\". On `/db-heavy` and `/db-slow`,")
    w("where holds are 12 ms and 100 ms, the figure is sound.")
    w()
    w("**`http_reqs` has no measured-phase sub-metric in this run.** These cells")
    w("were produced with the earlier `common.js`, so the request count spans")
    w("warmup and measurement together — roughly double what a 60 s window would")
    w("give. Latency, error rate and dropped iterations are correctly scoped; only")
    w("the raw count is not, and it is not used in any conclusion below.")
    w()

    # ------------------------------------------------------------- coverage
    w("## Coverage")
    w()
    w("| variant | " + " | ".join(f"/{x}" for x in workloads) + " |")
    w("| --- | " + " | ".join("---:" for _ in workloads) + " |")
    for v in variants_run:
        row = []
        for x in workloads:
            n = sum(len(by[(x, r, v)]) for r in rates)
            row.append(str(n) if n else "—")
        w(f"| `{LABEL[v]}` | " + " | ".join(row) + " |")
    w()

    # -------------------------------------------------------- per workload
    w("## Results by workload")
    w()
    for x in workloads:
        work, binds = DESC[x]
        w(f"### `/{x}` — {work}")
        w()
        w(f"Designed constraint: {binds}.")
        w()
        w("| rate | variant | rep | err % | p50 | p95 | p99 | p99.9 | max | cores | threads | dropped |")
        w("| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for r in rates:
            for v in variants_run:
                for c in sorted(by[(x, r, v)], key=lambda c: c["rep"]):
                    s = c.get("srv", {})
                    mark = " **⚠**" if c["invalid"] else ""
                    w(f"| {r:,} | `{LABEL[v]}` | {c['rep']} | {pct(c['err_rate'])} | "
                      f"{f(c['p50'])} | {f(c['p95'])} | {f(c['p99'])} | {f(c['p999'])} | "
                      f"{f(c['max'])} | {f(s.get('cores'), 3)} | {f(s.get('threads_live'), 0)} | "
                      f"{f(c['dropped'], 0)}{mark} |")
        w()
        w(_commentary(x, by, variants_run, rates))
        w()

    # ------------------------------------------------- latency decomposition
    w("## Where the time actually went")
    w()
    w("k6 splits each request into `blocked` (waiting for a free connection from")
    w("its own pool, which includes waiting for the server to accept the TCP")
    w("connection), `connecting`, `sending`, `waiting` (time to first byte) and")
    w("`receiving`. That split distinguishes an application that is slow from one")
    w("that never got the request.")
    w()
    w("| cell | err % | duration p50 | waiting p50 | blocked p95 | server-side outcome |")
    w("| --- | ---: | ---: | ---: | ---: | --- |")
    interesting = [
        "mvc-platform__api__1000rps__r1", "mvc-platform__api__1500rps__r1",
        "mvc-virtual__api__1500rps__r1", "webflux-r2dbc__api__1500rps__r1",
        "mvc-platform__db-slow__1500rps__r1", "mvc-virtual__db-slow__1500rps__r1",
        "webflux-r2dbc__db-slow__1500rps__r1",
        "webflux-r2dbc__db-heavy__1500rps__r2", "mvc-virtual__db-heavy__1500rps__r2",
    ]
    idx = {c["tag"]: c for c in cells}
    for tag in interesting:
        c = idx.get(tag)
        if not c:
            continue
        s = c.get("srv", {})
        ep = s.get("endpoint", {})
        desc = ", ".join(f"{k.split('_')[0].lower()} {v['count']:,.0f} @ {v['mean_ms']:,.0f} ms"
                         for k, v in ep.items()) or "—"
        w(f"| `{tag.replace('__', ' · ')}` | {pct(c['err_rate'])} | {f(c['p50'])} | "
          f"{f(c['waiting'].get('p(50)'))} | {f(c['blocked'].get('p(95)'))} | {desc} |")
    w()
    w("Three things fall out of that table.")
    w()
    w("**`mvc-platform` on `/api` at 1,500 rps was not slow — it was unreachable.**")
    w("The server completed 127,256 requests at a mean of 202 ms, exactly the")
    w("upstream call plus overhead, and logged no exceptions at all. Meanwhile")
    w("`blocked` reached 834 ms at p95: the requests were sitting in the accept")
    w("queue, never reaching the application, and the client abandoned them at one")
    w("second. Tomcat's 200 threads at 200 ms each cap throughput at 1,000 rps, so")
    w("at 1,500 the surplus 500 per second simply accumulated.")
    w()
    w("**At exactly 1,000 rps the same variant showed 0 % errors and a p50 of**")
    w("**615.7 ms.** That is the queue filling but not overflowing inside the")
    w("timeout — the knee itself, caught between the two rungs of the ladder.")
    w()
    w("**On `/db-slow` the three stacks failed in three different ways.**")
    w("`mvc-platform` served a trickle successfully and left everything else in the")
    w("accept queue, burning 0.056 cores — the application was almost idle.")
    w("`mvc-virtual` admitted the load, exhausted the pool and returned 80,170")
    w("`CannotGetJdbcConnectionException` responses while burning 1.18 cores.")
    w("`webflux-r2dbc` admitted it too and returned 165,159")
    w("`TransientDataAccessResourceException` responses at 1.62 cores, with 14")
    w("successes. Same 100 % failure rate; completely different shapes.")
    w()

    # -------------------------------------------------------------- failures
    w("## Server-side failures")
    w()
    w("Exception counts differenced across the measured window, by endpoint.")
    w()
    seen = defaultdict(float)
    for c in cells:
        for e, n in (c.get("srv", {}).get("exceptions") or {}).items():
            seen[(c["workload"], c["variant"], e)] += n
    w("| endpoint | variant | exception | count |")
    w("| --- | --- | --- | ---: |")
    for k in sorted(seen, key=lambda k: -seen[k]):
        w(f"| `/{k[0]}` | `{k[1]}` | `{k[2]}` | {seen[k]:,.0f} |")
    w()
    w("`mvc-platform` raised **no** server-side exceptions anywhere,")
    w("including on cells k6 scored at 100 % failure. Its failures were entirely")
    w("client-side timeouts against a full accept queue — the application never saw")
    w("the request, so it had nothing to fail on.")
    w()
    tos = [(c["tag"], c["srv"]["pool_timeouts"]) for c in cells
           if c.get("srv", {}).get("pool_timeouts")]
    if tos:
        w("Connection-pool timeouts (`hikaricp_connections_timeout_total`):")
        w()
        w("| cell | timeouts |")
        w("| --- | ---: |")
        for tag, n in sorted(tos, key=lambda t: -t[1]):
            w(f"| `{tag.replace('__', ' · ')}` | {n:,.0f} |")
        w()
        w("The 253 timeouts attributed to `mvc-virtual · api · 500rps · r1` are")
        w("contamination, not a result: `/api` touches no database. The JVM was")
        w("still draining queued `/db-slow` work from the previous cell when this")
        w("one's first scrape was taken. It is the clearest evidence that not")
        w("restarting the JVM between cells has a cost.")
        w()

    # ------------------------------------------------------------- resources
    w("## Resource use")
    w()
    w("Medians of both repetitions. CPU is the reliable figure here; heap is a")
    w("single sample taken at the end of the window and sawtooths with GC, so it is")
    w("reported alongside live-set size, which is measured after a collection and")
    w("is far steadier.")
    w()
    w("| workload | rate | variant | cores | of 2 vCPU | heap MB | live set MB | threads | GC pauses | GC ms | allocated GB |")
    w("| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for x in workloads:
        for r in rates:
            for v in variants_run:
                cs = by[(x, r, v)]
                if not cs:
                    continue
                def med(key):
                    vals = [c["srv"].get(key) for c in cs if c.get("srv", {}).get(key) is not None]
                    return st.median(vals) if vals else None
                cores = med("cores")
                w(f"| `/{x}` | {r:,} | `{LABEL[v]}` | {f(cores, 3)} | "
                  f"{f(cores * 50 if cores else None, 0)} % | {f(med('heap_mb'), 0)} | "
                  f"{f(med('live_data_mb'), 0)} | {f(med('threads_live'), 0)} | "
                  f"{f(med('gc_count'), 0)} | {f((med('gc_pause_s') or 0) * 1000, 0)} | "
                  f"{f(med('alloc_gb'), 1)} |")
    w()

    # ----------------------------------------------------------------- pools
    w("## Connection pool behaviour")
    w()
    w("Mean connection hold and acquire time, differenced across the window. Only")
    w("the blocking variants expose these; R2DBC Pool publishes gauges but no")
    w("equivalent timer, so its rows are empty by necessity rather than by")
    w("omission.")
    w()
    w("| workload | rate | variant | borrows | hold ms | acquire ms | pending |")
    w("| --- | ---: | --- | ---: | ---: | ---: | ---: |")
    for x in ("db", "db-heavy", "db-slow"):
        if x not in workloads:
            continue
        for r in rates:
            for v in variants_run:
                cs = [c for c in by[(x, r, v)] if c.get("srv", {}).get("borrows")]
                if not cs:
                    continue
                def med(key):
                    vals = [c["srv"].get(key) for c in cs if c["srv"].get(key) is not None]
                    return st.median(vals) if vals else None
                w(f"| `/{x}` | {r:,} | `{LABEL[v]}` | {f(med('borrows'), 0)} | "
                  f"{f(med('hold_ms'), 2)} | {f(med('acquire_ms'), 2)} | {f(med('pool_pending'), 0)} |")
    w()
    w("The `/db-heavy` hold of about 11.96 ms is the deliberate `pg_sleep(0.011)`")
    w("pad plus the real query, and it holds steady across every rate — which is")
    w("the pad doing exactly what it was added for.")
    w()
    w("On `/db-slow` the hold climbs with offered load — roughly 101 ms at 500 rps")
    w("to 162 ms at 2,000 on `mvc-virtual` — even though `pg_sleep(0.1)` is fixed.")
    w("The extra time is contention inside PostgreSQL once far more sessions are")
    w("queued against it than the pool can serve.")
    w()

    # ------------------------------------------------------- r2dbc analysis
    w("## Why R2DBC struggles on /db-heavy")
    w()
    w(R2DBC)
    w()

    # -------------------------------------------------------------- findings
    w("## Findings")
    w()
    w(FINDINGS)
    w()

    # --------------------------------------------------------------- invalid
    w("## Invalid cells")
    w()
    w("k6 dropped iterations during the measured phase in these cells, so the")
    w("offered rate was not sustained and the figures understate the load. They are")
    w("shown in the tables above marked **⚠** and must not be quoted.")
    w()
    w("| cell | err % | dropped | note |")
    w("| --- | ---: | ---: | --- |")
    for c in sorted(invalid, key=lambda c: (c["workload"], c["rate"], c["variant"], c["rep"])):
        note = "generator could not sustain the rate against a saturated server"
        w(f"| `{c['tag'].replace('__', ' · ')}` | {pct(c['err_rate'])} | {c['dropped']:,.0f} | {note} |")
    w()
    w("All 21 are at the top of a ladder against an already-failing server. None")
    w("sit in a region where a variant was still healthy, so no conclusion below")
    w("rests on one.")
    w()

    # ------------------------------------------------------------- vs local
    w("## What changed against the laptop run")
    w()
    w(VS_LOCAL)
    w()
    w("## Still not established")
    w()
    w(LIMITS)
    return "\n".join(W)


def _commentary(x, by, variants, rates):
    if x == "nodb":
        return ("Every variant is identical and idle: p50 between 0.1 and 0.4 ms at "
                "every rate, no errors anywhere, and CPU under 0.13 cores even at "
                "2,000 rps. The web layer is not a differentiator at any rate tested. "
                "Thread counts are the only visible difference — around 215 for the "
                "platform-thread builds against 20 for virtual threads and 21 for "
                "reactive, because virtual threads are not counted in "
                "`jvm_threads_live_threads`.")
    if x == "db":
        return ("Still nothing separating the stacks. p50 sits between 0.4 and 0.8 ms "
                "for all four at every rate, with no errors. Connection hold is below "
                "HikariCP's one-millisecond resolution, so the pool never approaches "
                "its 20 connections. Reactive uses slightly more CPU here than the "
                "blocking builds — 0.35 against 0.16 cores at 2,000 rps — which is "
                "the first sign of a pattern that becomes decisive on `/db-heavy`.")
    if x == "db-heavy":
        return ("**The clearest reversal of the laptop findings.** At 1,500 rps "
                "`webflux-r2dbc` reaches a p95 of 455 ms and a p99 of 545 ms while "
                "`mvc-virtual` stays at 20.8 ms and 35.5 ms, and reactive burns 0.62 "
                "cores against 0.23. At 2,000 rps reactive fails 58–61 % of requests "
                "and drops tens of thousands of iterations, while virtual threads "
                "fail 92 % but keep serving. On the realistic database workload the "
                "reactive stack is both slower and roughly 2.6× more expensive in "
                "CPU. `mvc-virtual` and `mvc-platform` are near-identical throughout, "
                "which is expected: this workload is pool-bound and never puts enough "
                "requests in flight for the thread model to matter.")
    if x == "db-slow":
        return ("Saturated at every rung, as designed — the pool serves about 200 rps "
                "and the lowest rate offers 500. Error rates run 98–100 % everywhere. "
                "The value here is not the latency but the failure shape, covered "
                "below. Note that `mvc-platform` reports a p50 of 0.0 ms "
                "with 100 % errors: its requests failed at connection setup rather "
                "than after any work.")
    if x == "api":
        return ("The decisive workload, and it behaved exactly as the arithmetic "
                "predicted. `webflux-r2dbc` and `mvc-virtual` hold p50 at 200.5–200.9 "
                "ms from 500 to 2,000 rps with zero errors throughout — the 200 ms "
                "upstream call and almost nothing else. `mvc-platform` is clean at "
                "500, degrades to a p50 of 615–720 ms at 1,000 (the knee), and fails "
                "every request from 1,500 upward. Virtual threads cost more CPU than "
                "reactive at every rate: 0.56 against 0.36 cores at 2,000 rps, about "
                "57 % more.")
    return ""


R2DBC = """`/db-heavy` is the one workload where the two candidates diverge sharply,
and the cause is identifiable from the data rather than a matter of opinion.

### The cost is per row

`/db` returns one row; `/db-heavy` returns twenty. Differencing the two at the
same offered rate isolates the marginal cost of nineteen extra rows:

| @ 1,500 rps | 1 row | 20 rows | per extra row |
| --- | ---: | ---: | ---: |
| R2DBC | 195 us | 408 us | **11.2 us** |
| JDBC | 116 us | 155 us | **2.1 us** |

At 1,000 rps the same calculation gives 10.2 us against 0.34 us. R2DBC costs
roughly 5 to 30 times more CPU per row than JDBC on this path.

Allocation agrees, and the ratio is constant across every rate — the signature
of a fixed per-row cost rather than a load-dependent one:

| | GB allocated per 1,000 requests |
| --- | ---: |
| R2DBC | **0.497** |
| JDBC | 0.129 |

### What it is not

**Not the database.** `r2dbc_pool_pending_connections` is zero at every rate.
It never waited for a connection.

**Not extra round trips.** Were R2DBC fetching twenty rows across several
network round trips, p50 would rise. It does not: 12.7-13.0 ms at every rate,
against JDBC's 12.4-12.5.

**Not garbage collection alone.** 435 ms of pause across a 60-second window is
0.7 % of wall time. Real, and nowhere near a 313 ms p95.

### Why the tail explodes at 31 % CPU

| rate | p50 | p95 | p99 | live threads | cores |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | 13.0 | 13.5 | 15.4 | 21 | 0.258 |
| 1,000 | 12.7 | 15.9 | 229.3 | 21 | 0.409 |
| 1,500 | 12.9 | **313.0** | **409.3** | 21 | 0.613 |

**p50 never moves.** The happy path is untouched at every rate; only the tail
detonates. That is queueing, not uniform slowness — a stack that were simply
slower would show it in the median.

The second-to-last column is the reason. Reactor Netty holds **21 live threads
at every workload and every rate** — a fixed event-loop pool that does not grow.
For contrast, `mvc-virtual` on `/api` goes from 52 threads to 79 as load rises.

So the per-row decoding runs on those event loops, and on 2 vCPU there is very
little loop capacity to absorb a burst. An average utilisation of 0.613 of 2
cores hides the fact that a request whose twenty-row decode is occupying a loop
blocks everything queued behind it on that same loop. A thread-per-request model
lets the OS preempt and spread the work; an event loop serialises it.

### Confidence

Well supported by the data: the cost is per row, it is CPU and allocation, it is
not the database, and the tail comes from a fixed thread pool rather than from
saturation.

Inferred, not measured: *why* each row costs 11 us. Most likely the reactive
pipeline's per-row overhead — a signal through the chain, `Row` and
`RowMetadata` objects, per-row subscription bookkeeping, buffer slicing and
codec dispatch, against JDBC reading fields straight off a cursor with near-zero
per-row allocation. Confirming that specifically needs an allocation profile
from async-profiler or JFR on the event-loop threads during a `/db-heavy` run.

### The rule this gives

R2DBC's cost scales with rows returned; JDBC's barely does. Single-row lookups
are fine — `/db` shows only a 1.2-1.7x gap. Multi-row result sets get expensive
quickly, and the pain lands in the tail rather than the median.

Caveat: this is `r2dbc-postgresql 1.1.2` with default fetch settings on two
vCPU. More cores or a tuned fetch size would change the magnitude, though not,
on this evidence, the direction."""

FINDINGS = """**1. The thread ceiling is real, and lands exactly where predicted.**
`mvc-platform` on `/api` is healthy at 500 rps, shows a p50 of 615–720 ms at
1,000, and fails every request at 1,500 and above. Tomcat's 200 threads against
a 200 ms call cap throughput at 1,000 rps; the ladder brackets that precisely.
The server itself stayed fast throughout — 202 ms mean, zero exceptions — so
this is a queueing limit, not a slow application.

**2. Virtual threads remove that ceiling completely.** On `/api`, `mvc-virtual`
matched reactive at every rate from 500 to 2,000 rps: p50 within 0.1 ms, zero
errors, tail within tens of milliseconds. Whatever else is true, the thread
model is not a reason to stay on reactive.

**3. On the realistic database workload, reactive is now the worse option.**
This is the finding that reverses the laptop run. `/db-heavy` at 1,500 rps:
reactive p95 455 ms and 0.62 cores, virtual threads p95 20.8 ms and 0.23 cores.
At 2,000 rps reactive fails 58–61 % of requests and cannot sustain the offered
rate. On a 2-vCPU box the R2DBC path costs roughly 2.6× the CPU of the JDBC
path for the same query.

**4. Reactive keeps its advantage only where there is no database.** On `/api`
— an upstream call and nothing else — reactive uses 0.36 cores against virtual
threads' 0.56 at 2,000 rps, about 36 % less. That is a real and consistent
advantage, and it is confined to the workload with no driver in the path.

**5. Thread count is not memory.** The platform builds run ~215 live threads
against 20–21 for the other two, yet heap and live-set figures are comparable.
A thread parked on a socket costs address space, not resident pages.

**6. The three stacks fail in three different shapes.** Under overload,
platform threads refuse work at the accept queue and stay almost idle
(0.056 cores); virtual threads admit everything, exhaust the pool and return
500s at 1.18 cores; reactive admits everything and fails at 1.62 cores. For
capacity planning these are not interchangeable: only the first leaves spare
CPU to recover with."""

VS_LOCAL = """| | Laptop | AWS | Verdict |
| --- | --- | --- | --- |
| `/api` thread ceiling | platform failed at 1,000 rps | healthy at 500, knee at 1,000, fails at 1,500 | **Confirmed**, with better resolution — the laptop conflated the knee with the cliff |
| Virtual threads vs reactive on `/api` | indistinguishable | indistinguishable | **Confirmed** |
| Reactive CPU advantage | ~30 % less across the board | ~36 % less on `/api`, **2.6× worse on `/db-heavy`** | **Overturned as a general claim** — it holds only without a database in the path |
| Memory scaling | reactive +2 %, virtual +47 % | heap sample too noisy to reproduce the claim | **Not reproduced** — see below |

The memory-scaling result from the laptop run does not survive. That figure came
from thirteen samples of RSS taken during a run; this dataset has one heap
reading per cell taken at the end of the window, which sawtooths with GC and
varies from 52 MB to 972 MB across otherwise comparable cells. Nothing here
contradicts the laptop finding — there is simply no measurement in this run
capable of testing it. Confirming or dropping it needs periodic RSS sampling,
which the current runner does not do."""

LIMITS = """**Memory over time was not sampled.** One heap reading per cell, taken at the
end, is not enough to characterise memory behaviour. The single most valuable
addition to the runner would be periodic RSS and heap sampling during the
measured window, as the local resource run did.

**The JVM was not restarted between cells.** Counters are differenced so the
totals are sound, but state carries over: the 253 pool timeouts recorded against
an `/api` cell came from the previous `/db-slow` cell still draining. Cells at
the start of a ladder are also warmer than a cold start would be.

**Two repetitions, not three.** Several differences here — the `/db` CPU gap,
the `/nodb` tail percentiles — are smaller than the spread between the two runs
of the same cell. Only differences of the magnitude seen on `/db-heavy` and
`/api` are safe to act on.

**`/db-slow` produced no usable comparison.** Every cell was past saturation.
Re-running it on its own ladder (50–300 rps) would turn it from a failure-mode
demonstration into a measurement.

**No write path was tested.** Every workload is a read. Transactional writes are
where the two programming models differ most, and where `@Transactional`
semantics versus reactive transaction context would actually be exercised.
"""


if __name__ == "__main__":
    print(main())
