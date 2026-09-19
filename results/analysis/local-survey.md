# Local survey — 2026-09-19

**Not quotable.** Load generator, all four variants, Postgres and the stub shared
one 6-core Windows laptop. Single 20s run per cell, 10s warmup, no repetitions.
Useful for the *shape* of differences and for validating the harness; not for
numbers that go in a decision memo.

Fixed for every run: `-Xms1g -Xmx1g -XX:+UseG1GC`, `POOL_SIZE=20`,
`UPSTREAM_DELAY_MS=200`, k6 v2.2.0, JDK 25.0.4, Spring Boot 4.1.1.

## Latency and errors

### `/nodb` @ 2,000 rps — web layer only

| variant | done/s | err% | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mvc-platform | 2000 | 0.00 | 0.0 | 0.5 | 1.6 | 32.5 |
| mvc-virtual | 2000 | 0.00 | 0.0 | 6.5 | **59.9** | **321.8** |
| webflux-r2dbc | 2000 | 0.00 | 0.0 | 0.5 | 2.6 | 53.9 |
| mvc-jpa | 2000 | 0.00 | 0.0 | 0.5 | 1.2 | 38.6 |

### `/db` @ 1,000 rps — cheap query, pool far from binding

| variant | done/s | err% | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mvc-platform | 1000 | 0.00 | 1.1 | 15.5 | 89.9 | 214.9 |
| mvc-virtual | 970 | 1.37 | 1.0 | 36.8 | **422.4** | 805.5 |
| webflux-r2dbc | 1000 | 0.00 | 1.1 | 14.7 | 90.9 | 152.1 |
| mvc-jpa | 1000 | 0.00 | 1.1 | 5.8 | 15.4 | 62.7 |

### `/db-heavy` @ 1,000 rps — 15ms hold, pool at ~72% utilisation

| variant | done/s | err% | p50 | p95 | p99 | max | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mvc-platform | 969 | 27.35 | 13.9 | 999.4 | 1891.1 | 2461.4 | **INVALID** (443 drops) |
| mvc-virtual | 964 | 23.81 | 406.6 | 1111.5 | 1375.5 | 1559.7 | |
| webflux-r2dbc | 987 | **5.53** | 17.0 | 331.3 | 1041.5 | 1211.2 | |
| mvc-jpa | 951 | **62.57** | 999.1 | 1002.8 | 1044.5 | 1133.3 | |

### `/api` @ 500 rps — ~105 in flight, under Tomcat's 200 threads

| variant | done/s | err% | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mvc-platform | 497 | 0.00 | 209.0 | 216.5 | 219.3 | 239.1 |
| mvc-virtual | 497 | 0.00 | 209.2 | 217.0 | 227.2 | 266.1 |
| webflux-r2dbc | 496 | 0.00 | 208.6 | 215.9 | 216.9 | 231.1 |
| mvc-jpa | 497 | 0.00 | 208.8 | 216.1 | 217.2 | 231.9 |

### `/api` @ 1,500 rps — ~300 in flight, past Tomcat's 200 threads

| variant | done/s | err% | p50 | p95 | p99 | max | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mvc-platform | 1421 | **100.00** | 999.8 | 1008.0 | 1039.7 | 1250.6 | |
| mvc-virtual | 1453 | **0.00** | 208.9 | 229.7 | 278.5 | 419.1 | |
| webflux-r2dbc | 1490 | **0.00** | 209.1 | 215.8 | 219.3 | 242.7 | |
| mvc-jpa | 1395 | **100.00** | 999.7 | 1319.7 | 2932.4 | 3465.7 | **INVALID** (1671 drops) |

## Server-side, sampled immediately after each run

### `/db-heavy` @ 1,000

| variant | live threads | heap MB | GC ms | GCs |
| --- | ---: | ---: | ---: | ---: |
| mvc-platform | 217 | 61 | 63 | 3 |
| mvc-virtual | 27 | 46 | 92 | 4 |
| webflux-r2dbc | 34 | 43 | 181 | 10 |
| mvc-jpa | 217 | **289** | 92 | 7 |

### `/api` @ 1,500

| variant | live threads | heap MB | GC ms | GCs |
| --- | ---: | ---: | ---: | ---: |
| mvc-platform | 329 | 319 | 172 | 5 |
| mvc-virtual | 173 | **465** | 198 | 5 |
| webflux-r2dbc | **32** | **19** | 59 | 3 |
| mvc-jpa | 427 | 476 | 123 | 4 |

## What holds up

**The `/api` cliff is exactly where the arithmetic said it would be.** At 500 rps
(~105 in flight) all four variants are indistinguishable — p50 209ms, zero
errors, differences inside noise. At 1,500 rps (~300 in flight, past Tomcat's
200 threads) `mvc-platform` and `mvc-jpa` fail *every single request*, while
`mvc-virtual` and `webflux-r2dbc` are untouched at p50 209ms. This is a cliff,
not a slope, and it lands where `docs/WORKLOADS.md` predicted before any code ran.

**Thread counts confirm the mechanism.** On `/api` at 1,500: webflux holds 32
threads, mvc-virtual 173 platform threads (carriers, plus virtual threads that do
not appear in this gauge), mvc-platform 329 and mvc-jpa 427 — both well past
their useful ceiling and paying for it.

**Virtual thread stacks live on the heap, and it shows.** On `/api` at 1,500,
mvc-virtual uses 465MB of heap against webflux's 19MB while serving the same load
at similar latency. Same throughput, ~24x the heap. That is the cost of carrying
a stack per in-flight request, and it is the concrete trade against reactive.

**Hibernate's memory cost is visible.** On `/db-heavy`, mvc-jpa holds 289MB of
heap against 43–61MB for every other variant on the same query — roughly 5x, for
the persistence context and entity hydration. It was also the worst performer on
that workload by a wide margin (62.57% errors).

## What does not hold up, and needs re-running on EC2

**mvc-virtual looks bad on short-task workloads, and it is probably an artefact.**
p99 of 59.9ms on `/nodb` and 422.4ms on `/db`, where every other variant is under
91ms. The likely cause is local contention: virtual threads run on a ForkJoinPool
with one carrier per core, so on a 6-core box also running k6, Postgres and the
stub, the carrier pool is starved in a way that 200 OS-scheduled platform threads
are not. This would disappear on a dedicated SUT. **Do not report this number
without re-measuring.**

**Two cells are INVALID** — k6 dropped iterations during the measured phase, so
the offered rate was not actually sustained and those rows understate the load.
Both are on the laptop's capacity, not the application's.

**`/db-heavy` degraded everywhere**, including variants that should have coped.
At 1,000 rps against a 1,387 rps pool knee, nothing should have been in trouble.
The whole machine was saturated. This workload needs the EC2 split before it says
anything.

**Single runs, no repetitions.** Earlier in the same session, `mvc-virtual` on
`/api` measured p99 205ms at 1,500 rps and p99 1,264ms at 1,000 rps — the *lower*
rate looking worse. That is the noise floor of this machine, and it is larger
than several of the differences tabulated above.

## Provisional reading

On the one workload where the machine was not the bottleneck — `/api` — the
result is clean and matches the theory: below the thread ceiling nothing
distinguishes the variants; above it, platform threads fail completely and both
alternatives are unaffected.

The interesting question for the rewrite is therefore not whether virtual threads
work. It is whether the ~24x heap difference against reactive matters at the load
the platform actually serves, given that one is a configuration flag and the
other is a rewrite.
