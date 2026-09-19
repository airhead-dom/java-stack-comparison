# Benchmark results — local survey

2026-09-19. One 6-core Windows laptop running load generator, application,
Postgres and stub together. **Indicative only, not quotable** — re-run on EC2 for
numbers that go in a decision.

JDK 25.0.4 · Spring Boot 4.1.1 · k6 v2.2.0 · `POOL_SIZE=20` · upstream delay 200ms

All latency values are **milliseconds**, percentiles of k6 `http_req_duration`.

---

## Latency

### `/nodb` @ 2,000 rps — web layer only
*median of 3 runs*

| variant | rps | err % | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mvc-platform | 2000 | 0.00 | 0.0 | 0.0 | 1.0 | 22.2 |
| mvc-virtual | 2000 | 0.00 | 0.0 | 0.0 | 1.0 | 21.8 |
| webflux-r2dbc | 2000 | 0.00 | 0.0 | 0.0 | 1.0 | 15.8 |
| mvc-jpa | 2000 | 0.00 | 0.0 | 0.0 | 1.0 | 24.9 |

### `/db` @ 1,000 rps — 1ms query
*median of 3 runs; per-run p99 shown*

| variant | rps | err % | p50 | p95 | p99 | max | p99 per run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| webflux-r2dbc | 1000 | 0.00 | 1.0 | 1.6 | 3.5 | 25.5 | 2.5 / 3.5 / 4.4 |
| mvc-platform | 1000 | 0.00 | 0.6 | 1.5 | 5.6 | 38.6 | 4.2 / 5.6 / 39.0 |
| mvc-virtual | 1000 | 0.00 | 0.5 | 1.4 | 11.7 | 47.1 | 4.9 / 11.7 / 19.0 |
| mvc-jpa | 1000 | 0.00 | 1.0 | 1.5 | 14.1 | 38.7 | 6.8 / 14.1 / 18.5 |

Spreads overlap — p99 here does not rank the variants.

### `/api` @ 500 rps — ~105 in flight

| variant | rps | err % | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mvc-platform | 497 | 0.00 | 209.0 | 216.5 | 219.3 | 239.1 |
| mvc-virtual | 497 | 0.00 | 209.2 | 217.0 | 227.2 | 266.1 |
| webflux-r2dbc | 496 | 0.00 | 208.6 | 215.9 | 216.9 | 231.1 |
| mvc-jpa | 497 | 0.00 | 208.8 | 216.1 | 217.2 | 231.9 |

### `/api` @ 1,000 rps — ~200 in flight, at Tomcat's 200-thread ceiling

| variant | rps | err % | p99 |
| --- | ---: | ---: | ---: |
| webflux-r2dbc | 996 | 0.00 | 217.8 |
| mvc-virtual | 996 | 0.00 | 217.9 |
| mvc-platform | 980 | **100.00** | 1199.7 |

### `/api` @ 1,500 rps — ~300 in flight

| variant | rps | err % | p50 | p95 | p99 | max | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| webflux-r2dbc | 1490 | 0.00 | 209.1 | 215.8 | 219.3 | 242.7 | |
| mvc-virtual | 1453 | 0.00 | 208.9 | 229.7 | 278.5 | 419.1 | |
| mvc-platform | 1421 | **100.00** | 999.8 | 1008.0 | 1039.7 | 1250.6 | |
| mvc-jpa | 1395 | **100.00** | 999.7 | 1319.7 | 2932.4 | 3465.7 | invalid |

### `/db-heavy` @ 1,000 rps — 15ms connection hold
*machine was saturated; provisional*

| variant | rps | err % | p50 | p95 | p99 | max | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| webflux-r2dbc | 987 | 5.53 | 17.0 | 331.3 | 1041.5 | 1211.2 | |
| mvc-virtual | 964 | 23.81 | 406.6 | 1111.5 | 1375.5 | 1559.7 | |
| mvc-platform | 969 | 27.35 | 13.9 | 999.4 | 1891.1 | 2461.4 | invalid |
| mvc-jpa | 951 | 62.57 | 999.1 | 1002.8 | 1044.5 | 1133.3 | |

---

## Resource usage

`/api` workload, `-Xms128m -Xmx1g -XX:+UseG1GC`.
`cores` = CPU-seconds per wall-second (1.000 = one core saturated).
RSS, heap and threads are the median of 13 samples taken 2s apart.

### @ 500 rps — all four healthy, identical work

| variant | cores | RSS MB | heap MB | nonheap MB | threads |
| --- | ---: | ---: | ---: | ---: | ---: |
| webflux-r2dbc | **0.222** | **303** | **63** | 86 | **31** |
| mvc-virtual | 0.315 | 349 | 129 | 79 | 197 |
| mvc-platform | 0.350 | 352 | 125 | 78 | 309 |
| mvc-jpa | 0.352 | 417 | 134 | 121 | 307 |

Relative to webflux-r2dbc:

| variant | CPU | RSS | heap | threads |
| --- | ---: | ---: | ---: | ---: |
| mvc-virtual | ×1.42 | ×1.15 | ×2.04 | ×6.4 |
| mvc-platform | ×1.58 | ×1.16 | ×1.98 | ×10.0 |
| mvc-jpa | ×1.59 | ×1.38 | ×2.13 | ×9.9 |

### @ 1,000 rps

| variant | cores | RSS MB | heap MB | threads | err % |
| --- | ---: | ---: | ---: | ---: | ---: |
| webflux-r2dbc | **0.380** | **310** | **52** | **31** | 0.00 |
| mvc-virtual | 0.517 | 514 | 178 | 568 | 0.00 |
| mvc-platform | 0.458 | 462 | 160 | 382 | 100.00 |

mvc-platform's figures are not comparable — it was failing every request.

### Scaling 500 → 1,000 rps

| variant | cores | RSS MB | heap MB |
| --- | --- | --- | --- |
| webflux-r2dbc | 0.222 → 0.380 | 303 → 310 (**+2%**) | 63 → 52 |
| mvc-virtual | 0.315 → 0.517 | 349 → 514 (**+47%**) | 129 → 178 |
| mvc-platform | 0.350 → 0.458 | 352 → 462 (+31%) | 125 → 160 |

---

## Findings

**1. Below ~200 concurrent requests, all four variants are identical.**
`/nodb`, `/db` and `/api` @ 500 show no meaningful difference in latency.

**2. Past Tomcat's 200-thread ceiling, platform threads fail completely.**
At `/api` 1,000 and 1,500 rps: mvc-platform and mvc-jpa return 100% errors while
mvc-virtual and webflux-r2dbc stay at p99 ~218ms. A cliff, not a slope. It lands
where `docs/WORKLOADS.md` predicted. Not a resource limit — mvc-platform had CPU
headroom and was under its heap ceiling when it collapsed.

**3. Reactive uses ~30% less CPU** than either blocking variant for identical
work. Virtual threads sit between the two (×1.42 vs ×1.58).

**4. Memory differs far less than thread counts suggest** — 15% RSS at 500 rps
despite 6–10× the threads. Parked threads cost address space, not resident pages.

**5. Reactive memory is flat in concurrency; virtual threads' is not.** Doubling
load moved reactive RSS +2% and virtual-thread RSS +47%. Two points only, but the
shapes differ.

**6. Hibernate is the most expensive option on memory** — ×1.38 RSS and 121MB
nonheap (Metaspace) at 500 rps, and worst on `/db-heavy` at 62.57% errors.

---

## Notes

- **One run per cell** except `/nodb` and `/db` (3 runs). Treat single-digit-percent
  differences as noise.
- **`invalid`** = k6 dropped iterations during measurement, so the offered rate
  was not sustained. Laptop capacity, not application behaviour.
- **Where errors are high, latency is floored by the 1,000ms timeout.** `err 100.00
  / p50 999.8` means every request exceeded one second, not that each took one
  second. Read errors first.
- **`/db-heavy` saturated the whole machine** and needs re-running on EC2.
- **Windows `WorkingSet64` ≠ Linux cgroup RSS.** Re-measure before sizing containers.

### Corrections to earlier drafts

- An earlier "24× heap" figure for virtual threads was wrong — single sample,
  committed heap, and a rate where one variant was failing. Actual ratio is ~2×
  at 500 rps and ~3.4× at 1,000 rps.
- An earlier p99 of 422ms for mvc-virtual on `/db` did not reproduce; it came
  from a 10s warmup that never reached steady state. JFR over ~50,000 requests
  showed 1 pinning event (class loading at startup) and 0 carrier-pool failures.

### For the EC2 runs

60s warmup minimum · 3 repetitions, report median with spread · take JFR with
`jcmd <pid> JFR.dump`, not `dumponexit` · health-check the stub before each run.
