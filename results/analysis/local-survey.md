# Local survey — 2026-09-19

**Not quotable.** Load generator, all four variants, Postgres and the stub shared
one 6-core Windows laptop. Useful for the *shape* of differences and for
validating the harness; not for numbers that go in a decision memo.

Fixed for every run: `-Xms1g -Xmx1g -XX:+UseG1GC`, `POOL_SIZE=20`,
`UPSTREAM_DELAY_MS=200`, k6 v2.2.0, JDK 25.0.4, Spring Boot 4.1.1.

| Section | Protocol | Trust |
| --- | --- | --- |
| `/nodb`, `/db` | median of 3, 20s warmup / 25s measure | reasonable |
| `/db-heavy`, `/api` | single run, 10s warmup / 20s measure | provisional |

The first pass used a 10s warmup that never reached steady state and produced a
figure that reversed on re-measurement (see [Retracted](#retracted)). `/nodb` and
`/db` were redone properly. `/db-heavy` and `/api` were not, and should be read
with that in mind — though the `/api` result has since been reproduced twice in
independent runs.

## Reading the tables

All latency figures are **milliseconds**, and are percentiles of k6's
`http_req_duration` — the time from a request being sent to its response being
fully received, measured client-side. `p99 ms = 278.5` means 99% of requests
completed in under 278.5ms and 1 in 100 took longer. The 500ms SLA is stated at
p99, so that is the column that decides pass or fail.

**Where errors are high, the latency columns are floored by the timeout.**
`TIMEOUT_MS` is 1000, so k6 abandoned any request still outstanding at one second
and recorded it as ~1000ms. A row reading `errors 100.00 / p50 999.8` means every
request exceeded one second — not that they took exactly one second. The true
latency is unknown and higher. Read error rate first; once it is non-zero the
percentiles stop describing how bad things actually are.

On `/api`, p50 decomposes cleanly: the stub sleeps 200ms, so `p50 ms = 208.9`
means the application added ~9ms of its own.

## Latency and errors

### `/nodb` @ 2,000 rps — web layer only

Median of three runs; individual p99s listed so the spread is visible.

| variant | completed rps | errors % | p50 ms | p95 ms | p99 ms | max ms | p99 per run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mvc-platform | 2000 | 0.00 | 0.0 | 0.0 | 1.0 | 22.2 | 0.6 / 1.0 / 2.0 |
| mvc-virtual | 2000 | 0.00 | 0.0 | 0.0 | 1.0 | 21.8 | 1.0 / 1.0 / 1.0 |
| webflux-r2dbc | 2000 | 0.00 | 0.0 | 0.0 | 1.0 | 15.8 | 1.0 / 1.0 / 1.0 |
| mvc-jpa | 2000 | 0.00 | 0.0 | 0.0 | 1.0 | 24.9 | 1.0 / 1.0 / 1.0 |

**All four are identical.** Web-layer overhead is unmeasurable at this rate in
every variant. No drops, no errors, full rate sustained.

### `/db` @ 1,000 rps — cheap query, pool far from binding

| variant | completed rps | errors % | p50 ms | p95 ms | p99 ms | max ms | p99 per run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| webflux-r2dbc | 1000 | 0.00 | 1.0 | 1.6 | 3.5 | 25.5 | 2.5 / 3.5 / 4.4 |
| mvc-platform | 1000 | 0.00 | 0.6 | 1.5 | 5.6 | 38.6 | 4.2 / 5.6 / 39.0 |
| mvc-virtual | 1000 | 0.00 | 0.5 | 1.4 | 11.7 | 47.1 | 4.9 / 11.7 / 19.0 |
| mvc-jpa | 1000 | 0.00 | 1.0 | 1.5 | 14.1 | 38.7 | 6.8 / 14.1 / 18.5 |

**p50 and p95 are effectively identical** across all four — fractions of a
millisecond apart on a 1ms query. The p99 ordering looks like a ranking, but the
per-run spreads overlap heavily: mvc-platform's three runs span 4.2 to 39.0ms,
wider than the gap between its median and anyone else's. With three repetitions
on a shared machine, **the p99 column here does not support ranking the
variants.**

What it does support: at 1,000 rps with a 1ms query nothing is under stress, and
every variant sustained the full rate with zero errors.

### `/db-heavy` @ 1,000 rps — 15ms hold, pool at ~72% utilisation

Single run, 10s warmup. Provisional.

| variant | completed rps | errors % | p50 ms | p95 ms | p99 ms | max ms | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mvc-platform | 969 | 27.35 | 13.9 | 999.4 | 1891.1 | 2461.4 | **INVALID** (443 drops) |
| mvc-virtual | 964 | 23.81 | 406.6 | 1111.5 | 1375.5 | 1559.7 | |
| webflux-r2dbc | 987 | 5.53 | 17.0 | 331.3 | 1041.5 | 1211.2 | |
| mvc-jpa | 951 | 62.57 | 999.1 | 1002.8 | 1044.5 | 1133.3 | |

### `/api` @ 500 rps — ~105 in flight, under Tomcat's 200 threads

| variant | completed rps | errors % | p50 ms | p95 ms | p99 ms | max ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mvc-platform | 497 | 0.00 | 209.0 | 216.5 | 219.3 | 239.1 |
| mvc-virtual | 497 | 0.00 | 209.2 | 217.0 | 227.2 | 266.1 |
| webflux-r2dbc | 496 | 0.00 | 208.6 | 215.9 | 216.9 | 231.1 |
| mvc-jpa | 497 | 0.00 | 208.8 | 216.1 | 217.2 | 231.9 |

### `/api` @ 1,500 rps — ~300 in flight, past Tomcat's 200 threads

| variant | completed rps | errors % | p50 ms | p95 ms | p99 ms | max ms | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mvc-platform | 1421 | **100.00** | 999.8 | 1008.0 | 1039.7 | 1250.6 | |
| mvc-virtual | 1453 | **0.00** | 208.9 | 229.7 | 278.5 | 419.1 | |
| webflux-r2dbc | 1490 | **0.00** | 209.1 | 215.8 | 219.3 | 242.7 | |
| mvc-jpa | 1395 | **100.00** | 999.7 | 1319.7 | 2932.4 | 3465.7 | **INVALID** (1671 drops) |

## Server-side, sampled immediately after each run

### `/db-heavy` @ 1,000

| variant | live threads | heap MB | GC total ms | GC count |
| --- | ---: | ---: | ---: | ---: |
| mvc-platform | 217 | 61 | 63 | 3 |
| mvc-virtual | 27 | 46 | 92 | 4 |
| webflux-r2dbc | 34 | 43 | 181 | 10 |
| mvc-jpa | 217 | **289** | 92 | 7 |

### `/api` @ 1,500

| variant | live threads | heap MB | GC total ms | GC count |
| --- | ---: | ---: | ---: | ---: |
| mvc-platform | 329 | 319 | 172 | 5 |
| mvc-virtual | 173 | **465** | 198 | 5 |
| webflux-r2dbc | **32** | **19** | 59 | 3 |
| mvc-jpa | 427 | 476 | 123 | 4 |

## What holds up

**The `/api` cliff is exactly where the arithmetic said it would be.** At 500 rps
(~105 in flight) all four variants are indistinguishable — p50 209ms, zero
errors. At 1,500 rps (~300 in flight, past Tomcat's 200 threads) `mvc-platform`
and `mvc-jpa` fail *every single request*, while `mvc-virtual` and
`webflux-r2dbc` are untouched at p50 209ms. A cliff, not a slope, landing where
`docs/WORKLOADS.md` predicted before any code ran. Reproduced in two independent
runs.

**Below the ceiling, nothing distinguishes the variants.** `/nodb` at 2,000 rps
and `/db` at 1,000 rps are flat across all four at p50 and p95 alike. The thread
model is invisible until a resource is actually scarce — which is the other half
of the rewrite answer.

**Thread counts confirm the mechanism.** On `/api` at 1,500: webflux holds 32
threads, mvc-virtual 173 platform threads (carriers; virtual threads do not
appear in this gauge), mvc-platform 329 and mvc-jpa 427 — both past their useful
ceiling and paying for it.

**Virtual thread stacks live on the heap, and it shows.** On `/api` at 1,500,
mvc-virtual uses 465MB of heap against webflux's 19MB while serving the same load
at similar latency — roughly 24x, for carrying a stack per in-flight request.
That is the concrete trade against reactive.

**Hibernate's memory cost is visible.** On `/db-heavy`, mvc-jpa holds 289MB of
heap against 43–61MB for every other variant on the same query — roughly 5x, for
the persistence context and entity hydration. It was also the worst performer on
that workload (62.57% errors).

## Retracted

**mvc-virtual's poor short-task percentiles were an artefact.**

The first pass showed `mvc-virtual` at p99 422.4ms on `/db` and 59.9ms on
`/nodb`, against single-digit milliseconds elsewhere — which read as virtual
threads being the worst option available. Neither reproduces.

Re-run with a 20s warmup instead of 10s, three repetitions:

| workload | mvc-platform | mvc-virtual | first-pass claim |
| --- | ---: | ---: | --- |
| `/nodb` p99 | 1.0 ms | 1.0 ms | 59.9 ms |
| `/db` p99 | 5.6 ms | 11.7 ms | 422.4 ms |

On `/nodb` the two are identical. On `/db` the medians differ by 6ms with
overlapping spreads — not a ranking. The original figures were single unrepeated
runs that never left warmup.

**Not pinning either.** A flight recording over ~50,000 requests contains **one**
`jdk.VirtualThreadPinned` event, 33.9ms, on first-time class loading of a Hikari
proxy inside `ClassLoader.loadClass` — a startup artefact that cannot recur once
the class is loaded. Zero `jdk.VirtualThreadSubmitFailed`, so the carrier pool
was never exhausted.

*Method note:* the first attempt at that check read `0 events` from 0-byte files.
`dumponexit` needs a graceful shutdown and the JVMs were hard-killed, so nothing
was written. Recordings must be taken with `jcmd <pid> JFR.dump` while the
process is alive.

## Still unreliable

**`/db-heavy` degraded everywhere**, including variants that should have coped.
At 1,000 rps against a 1,387 rps pool knee nothing should have been in trouble.
The whole machine was saturated. Says nothing until the EC2 split.

**Two cells are INVALID** — k6 dropped iterations during the measured phase, so
the offered rate was not sustained and those rows understate the load. Both are
the laptop's capacity, not the application's.

**`/db-heavy` is a single run** at the short warmup and has not been reproduced.
`/api` is also a single run per rate, but its cliff has since appeared in two
independent runs, so the shape is trustworthy even if the exact figures are not.

## Provisional reading

On the workloads where the machine was not the bottleneck the picture is
consistent: **below the thread ceiling nothing distinguishes the four variants,
and above it platform threads fail completely while both alternatives are
unaffected.**

So the question for the rewrite is not whether virtual threads work — on every
clean workload they match reactive. It is whether the ~24x heap difference
against reactive matters at the load the platform actually serves, given that
`mvc-virtual` is a configuration flag and `webflux-r2dbc` is a rewrite.

## For the EC2 runs

- **60s warmup minimum.** 10s produced a figure that reversed on re-measurement;
  20s was adequate here but is not much margin.
- **Three repetitions, report the median, and show the spread.** Several
  differences in the first pass were smaller than the noise between runs.
- **Take JFR with `jcmd <pid> JFR.dump`**, not `dumponexit`.
