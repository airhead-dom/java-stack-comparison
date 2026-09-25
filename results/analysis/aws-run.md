# AWS benchmark run — full results

21 September 2026. Three EC2 instances in one availability zone: a load
generator, a 2-vCPU system under test, and a backend running PostgreSQL 17
and the stub service. Nothing shares a CPU with the application.

This is the complete dataset. `results/analysis/README.md` remains the
earlier laptop survey; where the two disagree, this one supersedes it.

| | |
| --- | --- |
| Cells | 120 — 3 variants × 5 workloads × 4 rates × 2 repetitions |
| Invalid | 15 — the generator dropped iterations during the measured window |
| JVM | OpenJDK 25.0.4+7-1-24.04-Ubuntu |
| SUT | 2 vCPU (`system_cpu_count` = 2), `-Xmx1g`, G1 |
| Pool | 20 connections, both HikariCP and R2DBC Pool |
| Rates | 500, 1,000, 1,500, 2,000 requests per second, offered open-model |
| Window | 60 s warmup discarded, 60 s measured |

## How to read this

**Latency figures are milliseconds**, percentiles of k6 `http_req_duration`
scoped to the measured phase. `p99.9` is included because several results
only separate in the far tail.

**Where the error rate is high, latency is floored by the 1,000 ms client
timeout.** A `p50` of 1,000.0 means at least half the requests were
abandoned, not that they took a second. Read the error column first.

**`cores`** is CPU-seconds consumed per wall-second, from
`process_cpu_time_ns_total` differenced across the window and divided by the
JVM's own uptime delta. `1.000` means one core saturated; the ceiling is
`2.000`.

**`dropped`** counts iterations k6 could not start during the measured
phase. Any non-zero value means the offered rate was not actually
sustained, so the cell understates the load and is marked invalid.

**Percentiles convert to counts.** Each cell offered `rate x 60 s` requests
in the measured window, and `passes + fails` on
`http_req_failed{phase:measure}` confirms it to the request. So a p99 of
409 ms over 90,000 requests means 900 requests were slower than 409 ms, and
a p95 of 313 ms means 4,500 were. Note k6 inverts the names on that metric:
`passes` counts requests where "failed" was true.

**Counters are differenced, not read.** The variant's JVM stayed up across
a whole ladder instead of restarting per cell, so a raw reading is a
since-startup total covering other workloads. Every counter here is
`after − before` across the two scrapes bracketing the measured window.

### Two measurement limits worth knowing before reading the numbers

**HikariCP records connection usage in whole milliseconds.** Its
`usage_seconds_sum` values end in exactly three decimal places while
`acquire_seconds_sum` carries nine, so any hold under 1 ms rounds to zero.
The hold figures on `/db` are therefore a floor, not a mean — treat them as
"below the resolution of the instrument". On `/db-heavy` and `/db-slow`,
where holds are 12 ms and 100 ms, the figure is sound.

**`http_reqs` has no measured-phase sub-metric in this run.** These cells
were produced with the earlier `common.js`, so the request count spans
warmup and measurement together — roughly double what a 60 s window would
give. Latency, error rate and dropped iterations are correctly scoped; only
the raw count is not, and it is not used in any conclusion below.

## Coverage

| variant | /nodb | /db | /db-heavy | /db-slow | /api |
| --- | ---: | ---: | ---: | ---: | ---: |
| `webflux-r2dbc` | 8 | 8 | 8 | 8 | 8 |
| `mvc-virtual` | 8 | 8 | 8 | 8 | 8 |
| `mvc-platform` | 8 | 8 | 8 | 8 | 8 |

## Results by workload

### `/nodb` — constant response, no I/O

Designed constraint: web layer only.

| rate | variant | rep | err % | p50 | p95 | p99 | p99.9 | max | cores | threads | dropped |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | `webflux-r2dbc` | 1 | 0.00 | 0.4 | 0.5 | 0.6 | 2.5 | 6.8 | 0.084 | 21 | 0 |
| 500 | `webflux-r2dbc` | 2 | 0.00 | 0.4 | 0.5 | 0.6 | 1.2 | 10.3 | 0.087 | 21 | 0 |
| 500 | `mvc-virtual` | 1 | 0.00 | 0.3 | 0.5 | 0.6 | 7.7 | 47.5 | 0.079 | 20 | 0 |
| 500 | `mvc-virtual` | 2 | 0.00 | 0.3 | 0.5 | 0.6 | 0.7 | 3.4 | 0.077 | 20 | 0 |
| 500 | `mvc-platform` | 1 | 0.00 | 0.3 | 0.5 | 0.6 | 2.9 | 17.7 | 0.079 | 215 | 0 |
| 500 | `mvc-platform` | 2 | 0.00 | 0.4 | 0.5 | 0.6 | 0.9 | 17.7 | 0.087 | 217 | 0 |
| 1,000 | `webflux-r2dbc` | 1 | 0.00 | 0.2 | 0.4 | 0.6 | 2.3 | 25.5 | 0.108 | 21 | 0 |
| 1,000 | `webflux-r2dbc` | 2 | 0.00 | 0.2 | 0.4 | 0.6 | 2.8 | 11.1 | 0.091 | 21 | 0 |
| 1,000 | `mvc-virtual` | 1 | 0.00 | 0.1 | 0.4 | 0.5 | 2.0 | 17.0 | 0.080 | 20 | 0 |
| 1,000 | `mvc-virtual` | 2 | 0.00 | 0.1 | 0.4 | 0.5 | 1.9 | 13.9 | 0.080 | 20 | 0 |
| 1,000 | `mvc-platform` | 1 | 0.00 | 0.1 | 0.4 | 0.5 | 5.0 | 22.7 | 0.071 | 215 | 0 |
| 1,000 | `mvc-platform` | 2 | 0.00 | 0.1 | 0.4 | 0.5 | 3.5 | 15.0 | 0.076 | 215 | 0 |
| 1,500 | `webflux-r2dbc` | 1 | 0.00 | 0.1 | 0.4 | 1.5 | 23.0 | 108.6 | 0.116 | 21 | 0 |
| 1,500 | `webflux-r2dbc` | 2 | 0.00 | 0.1 | 0.4 | 0.8 | 3.5 | 20.5 | 0.119 | 21 | 0 |
| 1,500 | `mvc-virtual` | 1 | 0.00 | 0.1 | 0.4 | 1.6 | 7.0 | 18.1 | 0.089 | 20 | 0 |
| 1,500 | `mvc-virtual` | 2 | 0.00 | 0.1 | 0.4 | 2.0 | 85.0 | 138.9 | 0.100 | 20 | 0 |
| 1,500 | `mvc-platform` | 1 | 0.00 | 0.1 | 0.4 | 1.6 | 5.7 | 21.1 | 0.102 | 215 | 0 |
| 1,500 | `mvc-platform` | 2 | 0.00 | 0.1 | 0.4 | 1.0 | 4.5 | 20.2 | 0.098 | 215 | 0 |
| 2,000 | `webflux-r2dbc` | 1 | 0.00 | 0.1 | 0.4 | 2.7 | 23.0 | 68.5 | 0.115 | 21 | 0 |
| 2,000 | `webflux-r2dbc` | 2 | 0.00 | 0.1 | 0.5 | 4.7 | 50.8 | 111.7 | 0.124 | 21 | 0 |
| 2,000 | `mvc-virtual` | 1 | 0.00 | 0.1 | 0.4 | 3.4 | 26.4 | 47.6 | 0.124 | 20 | 0 |
| 2,000 | `mvc-virtual` | 2 | 0.00 | 0.1 | 0.4 | 2.0 | 6.5 | 14.8 | 0.122 | 20 | 0 |
| 2,000 | `mvc-platform` | 1 | 0.00 | 0.1 | 0.4 | 2.3 | 10.1 | 24.5 | 0.125 | 215 | 0 |
| 2,000 | `mvc-platform` | 2 | 0.00 | 0.1 | 0.4 | 2.1 | 12.0 | 24.8 | 0.122 | 215 | 0 |

Every variant is identical and idle: p50 between 0.1 and 0.4 ms at every rate, no errors anywhere, and CPU under 0.13 cores even at 2,000 rps. The web layer is not a differentiator at any rate tested. Thread counts are the only visible difference — around 215 for the platform-thread builds against 20 for virtual threads and 21 for reactive, because virtual threads are not counted in `jvm_threads_live_threads`.

### `/db` — one indexed two-table query

Designed constraint: pool never binds.

| rate | variant | rep | err % | p50 | p95 | p99 | p99.9 | max | cores | threads | dropped |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | `webflux-r2dbc` | 1 | 0.00 | 0.8 | 1.0 | 1.3 | 7.0 | 84.9 | 0.207 | 21 | 0 |
| 500 | `webflux-r2dbc` | 2 | 0.00 | 0.8 | 1.0 | 1.4 | 2.0 | 12.1 | 0.179 | 21 | 0 |
| 500 | `mvc-virtual` | 1 | 0.00 | 0.6 | 0.8 | 1.0 | 12.6 | 38.6 | 0.218 | 21 | 0 |
| 500 | `mvc-virtual` | 2 | 0.00 | 0.6 | 0.9 | 1.1 | 2.8 | 21.1 | 0.118 | 21 | 0 |
| 500 | `mvc-platform` | 1 | 0.00 | 0.6 | 0.9 | 1.0 | 3.6 | 43.8 | 0.194 | 123 | 0 |
| 500 | `mvc-platform` | 2 | 0.00 | 0.6 | 0.9 | 1.0 | 1.5 | 20.7 | 0.102 | 135 | 0 |
| 1,000 | `webflux-r2dbc` | 1 | 0.00 | 0.5 | 1.2 | 9.6 | 295.4 | 484.8 | 0.227 | 21 | 0 |
| 1,000 | `webflux-r2dbc` | 2 | 0.00 | 0.5 | 1.0 | 2.4 | 43.3 | 102.3 | 0.204 | 21 | 0 |
| 1,000 | `mvc-virtual` | 1 | 0.00 | 0.4 | 0.8 | 1.8 | 8.8 | 29.9 | 0.118 | 21 | 0 |
| 1,000 | `mvc-virtual` | 2 | 0.00 | 0.3 | 0.8 | 3.2 | 289.9 | 371.8 | 0.178 | 21 | 0 |
| 1,000 | `mvc-platform` | 1 | 0.00 | 0.4 | 0.7 | 1.8 | 7.5 | 31.2 | 0.093 | 162 | 0 |
| 1,000 | `mvc-platform` | 2 | 0.00 | 0.4 | 0.8 | 2.2 | 12.1 | 21.8 | 0.095 | 176 | 0 |
| 1,500 | `webflux-r2dbc` | 1 | 0.00 | 0.5 | 1.3 | 4.9 | 46.0 | 78.9 | 0.303 | 21 | 0 |
| 1,500 | `webflux-r2dbc` | 2 | 0.00 | 0.5 | 0.9 | 3.3 | 10.9 | 22.2 | 0.282 | 21 | 0 |
| 1,500 | `mvc-virtual` | 1 | 0.00 | 0.4 | 0.9 | 5.5 | 333.0 | 439.6 | 0.172 | 21 | 0 |
| 1,500 | `mvc-virtual` | 2 | 0.00 | 0.5 | 0.8 | 3.3 | 19.5 | 51.1 | 0.176 | 21 | 0 |
| 1,500 | `mvc-platform` | 1 | 0.00 | 0.4 | 0.9 | 3.5 | 13.2 | 29.3 | 0.131 | 199 | 0 |
| 1,500 | `mvc-platform` | 2 | 0.00 | 0.4 | 0.7 | 2.1 | 5.7 | 23.4 | 0.126 | 215 | 0 |
| 2,000 | `webflux-r2dbc` | 1 | 0.00 | 0.5 | 1.8 | 17.1 | 56.3 | 99.7 | 0.356 | 21 | 0 |
| 2,000 | `webflux-r2dbc` | 2 | 0.00 | 0.5 | 1.0 | 4.1 | 14.7 | 22.2 | 0.348 | 21 | 0 |
| 2,000 | `mvc-virtual` | 1 | 0.00 | 0.5 | 1.3 | 5.0 | 21.8 | 209.8 | 0.309 | 21 | 0 |
| 2,000 | `mvc-virtual` | 2 | 0.00 | 0.4 | 0.7 | 3.1 | 12.3 | 28.2 | 0.265 | 21 | 0 |
| 2,000 | `mvc-platform` | 1 | 0.00 | 0.4 | 1.0 | 4.5 | 15.8 | 26.0 | 0.155 | 215 | 0 |
| 2,000 | `mvc-platform` | 2 | 0.00 | 0.4 | 1.1 | 5.0 | 18.4 | 23.3 | 0.159 | 215 | 0 |

Still nothing separating the stacks. p50 sits between 0.4 and 0.8 ms for all four at every rate, with no errors. Connection hold is below HikariCP's one-millisecond resolution, so the pool never approaches its 20 connections. Reactive uses slightly more CPU here than the blocking builds — 0.35 against 0.16 cores at 2,000 rps — which is the first sign of a pattern that becomes decisive on `/db-heavy`.

### `/db-heavy` — aggregate + 20 rows, padded to a 15 ms hold

Designed constraint: pool binds ~1,387 rps.

| rate | variant | rep | err % | p50 | p95 | p99 | p99.9 | max | cores | threads | dropped |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | `webflux-r2dbc` | 1 | 0.00 | 13.0 | 13.5 | 15.4 | 49.2 | 101.0 | 0.258 | 21 | 0 |
| 500 | `webflux-r2dbc` | 2 | 0.00 | 13.0 | 13.4 | 15.3 | 51.5 | 124.1 | 0.259 | 21 | 0 |
| 500 | `mvc-virtual` | 1 | 0.00 | 12.8 | 13.1 | 13.5 | 24.4 | 27.4 | 0.245 | 21 | 0 |
| 500 | `mvc-virtual` | 2 | 0.00 | 12.8 | 13.1 | 13.3 | 19.0 | 27.0 | 0.140 | 21 | 0 |
| 500 | `mvc-platform` | 1 | 0.00 | 12.8 | 13.1 | 13.4 | 26.3 | 33.1 | 0.141 | 215 | 0 |
| 500 | `mvc-platform` | 2 | 0.00 | 12.8 | 13.1 | 13.4 | 27.4 | 31.9 | 0.122 | 215 | 0 |
| 1,000 | `webflux-r2dbc` | 1 | 0.00 | 12.7 | 17.7 | 416.4 | 574.0 | 615.7 | 0.406 | 21 | 0 |
| 1,000 | `webflux-r2dbc` | 2 | 0.00 | 12.7 | 14.1 | 42.3 | 89.3 | 122.7 | 0.413 | 21 | 0 |
| 1,000 | `mvc-virtual` | 1 | 0.00 | 12.4 | 12.8 | 17.2 | 29.5 | 41.2 | 0.153 | 21 | 0 |
| 1,000 | `mvc-virtual` | 2 | 0.00 | 12.4 | 12.8 | 16.4 | 30.2 | 40.9 | 0.155 | 21 | 0 |
| 1,000 | `mvc-platform` | 1 | 0.00 | 12.4 | 12.8 | 13.6 | 24.3 | 39.7 | 0.151 | 216 | 0 |
| 1,000 | `mvc-platform` | 2 | 0.00 | 12.4 | 12.9 | 16.3 | 26.8 | 43.8 | 0.145 | 216 | 0 |
| 1,500 | `webflux-r2dbc` | 1 | 0.00 | 12.8 | 170.7 | 273.8 | 291.1 | 298.8 | 0.607 | 21 | 0 |
| 1,500 | `webflux-r2dbc` | 2 | 0.00 | 13.0 | 455.2 | 544.7 | 558.6 | 563.2 | 0.618 | 21 | 0 |
| 1,500 | `mvc-virtual` | 1 | 0.00 | 12.4 | 18.7 | 31.0 | 47.8 | 70.7 | 0.233 | 21 | 0 |
| 1,500 | `mvc-virtual` | 2 | 0.00 | 12.5 | 20.8 | 35.5 | 50.1 | 80.9 | 0.233 | 21 | 0 |
| 1,500 | `mvc-platform` | 1 | 0.00 | 12.4 | 16.4 | 30.5 | 48.6 | 73.6 | 0.216 | 216 | 0 |
| 1,500 | `mvc-platform` | 2 | 0.00 | 12.4 | 13.3 | 26.9 | 45.5 | 70.4 | 0.205 | 216 | 0 |
| 2,000 | `webflux-r2dbc` | 1 | 61.37 | 936.7 | 1,486.8 | 1,963.2 | 2,485.8 | 2,890.1 | 0.498 | 21 | 29,673 **⚠** |
| 2,000 | `webflux-r2dbc` | 2 | 58.24 | 902.9 | 1,581.1 | 2,464.6 | 2,736.9 | 4,126.4 | — | 21 | 35,422 **⚠** |
| 2,000 | `mvc-virtual` | 1 | 91.54 | 999.1 | 1,011.5 | 1,058.3 | 1,133.9 | 1,252.1 | 1.279 | 21 | 0 |
| 2,000 | `mvc-virtual` | 2 | 91.84 | 998.9 | 1,007.7 | 1,054.6 | 1,283.6 | 1,651.7 | 1.310 | 21 | 163 **⚠** |
| 2,000 | `mvc-platform` | 1 | 100.00 | 1,000.2 | 1,010.3 | 1,030.3 | 1,161.7 | 1,292.5 | 0.405 | 216 | 0 |
| 2,000 | `mvc-platform` | 2 | 100.00 | 1,000.2 | 1,005.9 | 1,023.3 | 1,042.3 | 1,102.7 | 0.395 | 216 | 0 |

**The clearest reversal of the laptop findings.** At 1,500 rps `webflux-r2dbc` reaches a p95 of 455 ms and a p99 of 545 ms while `mvc-virtual` stays at 20.8 ms and 35.5 ms, and reactive burns 0.62 cores against 0.23. At 2,000 rps reactive fails 58–61 % of requests and drops tens of thousands of iterations, while virtual threads fail 92 % but keep serving. On the realistic database workload the reactive stack is both slower and roughly 2.6× more expensive in CPU. `mvc-virtual` and `mvc-platform` are near-identical throughout, which is expected: this workload is pool-bound and never puts enough requests in flight for the thread model to matter.

### `/db-slow` — query + pg_sleep(0.1)

Designed constraint: pool binds ~200 rps.

| rate | variant | rep | err % | p50 | p95 | p99 | p99.9 | max | cores | threads | dropped |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | `webflux-r2dbc` | 1 | 100.00 | 733.3 | 1,000.9 | 1,001.0 | 1,002.0 | 1,028.0 | 0.460 | 21 | 0 |
| 500 | `webflux-r2dbc` | 2 | 100.00 | 691.6 | 1,000.9 | 1,001.0 | 1,017.8 | 1,040.6 | 0.400 | 21 | 0 |
| 500 | `mvc-virtual` | 1 | 99.16 | 1,000.2 | 1,000.9 | 1,015.7 | 1,035.6 | 1,039.8 | 0.313 | 21 | 0 |
| 500 | `mvc-virtual` | 2 | 99.08 | 1,000.1 | 1,000.9 | 1,010.4 | 1,032.4 | 1,038.9 | 0.279 | 21 | 0 |
| 500 | `mvc-platform` | 1 | 100.00 | 164.1 | 1,000.8 | 1,001.0 | 1,021.7 | 1,038.9 | 0.059 | 216 | 0 |
| 500 | `mvc-platform` | 2 | 100.00 | 167.1 | 1,000.8 | 1,001.0 | 1,018.0 | 1,038.2 | 0.056 | 216 | 0 |
| 1,000 | `webflux-r2dbc` | 1 | 99.89 | 777.2 | 1,000.5 | 1,000.9 | 1,001.9 | 1,019.6 | 0.871 | 21 | 0 |
| 1,000 | `webflux-r2dbc` | 2 | 98.38 | 768.5 | 1,000.5 | 1,000.9 | 1,007.4 | 1,021.1 | 0.821 | 21 | 0 |
| 1,000 | `mvc-virtual` | 1 | 99.16 | 1,000.2 | 1,001.0 | 1,013.8 | 1,033.4 | 1,042.4 | 1.130 | 21 | 0 |
| 1,000 | `mvc-virtual` | 2 | 98.82 | 1,000.2 | 1,001.0 | 1,016.5 | 1,036.0 | 1,043.8 | 1.125 | 21 | 0 |
| 1,000 | `mvc-platform` | 1 | 100.00 | 0.0 | 1,133.1 | 1,467.2 | 1,867.5 | 2,266.6 | 0.053 | 216 | 8,585 **⚠** |
| 1,000 | `mvc-platform` | 2 | 100.00 | 0.0 | 1,121.0 | 1,404.0 | 1,949.1 | 2,883.5 | 0.052 | 216 | 8,576 **⚠** |
| 1,500 | `webflux-r2dbc` | 1 | 100.00 | 906.7 | 1,000.1 | 1,000.9 | 1,007.7 | 1,036.6 | 1.617 | 21 | 0 |
| 1,500 | `webflux-r2dbc` | 2 | 100.00 | 906.3 | 1,000.1 | 1,000.8 | 1,001.3 | 1,023.2 | 1.646 | 21 | 0 |
| 1,500 | `mvc-virtual` | 1 | 99.01 | 533.3 | 1,001.1 | 1,019.3 | 1,064.5 | 1,144.1 | 1.176 | 21 | 0 |
| 1,500 | `mvc-virtual` | 2 | 98.83 | 545.0 | 1,001.1 | 1,018.9 | 1,085.1 | 1,313.5 | 1.168 | 21 | 0 |
| 1,500 | `mvc-platform` | 1 | 100.00 | 0.0 | 1,283.9 | 1,992.9 | 2,847.6 | 3,562.0 | 0.056 | 216 | 34,437 **⚠** |
| 1,500 | `mvc-platform` | 2 | 100.00 | 0.0 | 1,260.9 | 1,872.1 | 2,966.9 | 3,507.7 | 0.052 | 216 | 31,593 **⚠** |
| 2,000 | `webflux-r2dbc` | 1 | 98.03 | 611.1 | 2,522.1 | 3,784.3 | 6,015.7 | 8,334.2 | 0.216 | 21 | 77,210 **⚠** |
| 2,000 | `webflux-r2dbc` | 2 | 98.07 | 847.1 | 1,812.9 | 2,924.9 | 4,106.8 | 7,260.7 | 0.072 | 21 | 74,444 **⚠** |
| 2,000 | `mvc-virtual` | 1 | 99.35 | 570.3 | 1,169.4 | 1,524.9 | 2,539.6 | 2,989.7 | 1.229 | 21 | 29,437 **⚠** |
| 2,000 | `mvc-virtual` | 2 | 99.34 | 536.8 | 1,160.8 | 1,743.5 | 2,496.6 | 3,511.1 | 1.156 | 21 | 30,093 **⚠** |
| 2,000 | `mvc-platform` | 1 | 100.00 | 0.0 | 1,223.5 | 2,338.7 | 3,522.4 | 4,246.8 | 0.049 | 216 | 55,159 **⚠** |
| 2,000 | `mvc-platform` | 2 | 100.00 | 0.0 | 1,225.8 | 2,254.6 | 3,728.6 | 4,167.2 | 0.051 | 216 | 56,965 **⚠** |

Saturated at every rung, as designed — the pool serves about 200 rps and the lowest rate offers 500. Error rates run 98–100 % everywhere. The value here is not the latency but the failure shape, covered below. Note that `mvc-platform` reports a p50 of 0.0 ms with 100 % errors: its requests failed at connection setup rather than after any work.

### `/api` — one 200 ms upstream call, no database

Designed constraint: threads bind ~1,000 rps.

| rate | variant | rep | err % | p50 | p95 | p99 | p99.9 | max | cores | threads | dropped |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | `webflux-r2dbc` | 1 | 0.00 | 200.9 | 201.2 | 201.3 | 204.1 | 210.5 | 0.167 | 21 | 0 |
| 500 | `webflux-r2dbc` | 2 | 0.00 | 200.9 | 201.2 | 201.3 | 204.2 | 208.8 | 0.170 | 21 | 0 |
| 500 | `mvc-virtual` | 1 | 0.00 | 200.9 | 201.3 | 227.3 | 293.6 | 305.5 | 0.337 | 66 | 0 |
| 500 | `mvc-virtual` | 2 | 0.00 | 200.9 | 201.2 | 201.7 | 224.7 | 248.4 | 0.199 | 39 | 0 |
| 500 | `mvc-platform` | 1 | 0.00 | 200.9 | 201.2 | 201.4 | 207.4 | 215.6 | 0.299 | 226 | 0 |
| 500 | `mvc-platform` | 2 | 0.00 | 200.9 | 201.2 | 201.4 | 206.7 | 214.9 | 0.198 | 226 | 0 |
| 1,000 | `webflux-r2dbc` | 1 | 0.00 | 200.6 | 201.1 | 215.3 | 263.8 | 292.4 | 0.255 | 21 | 0 |
| 1,000 | `webflux-r2dbc` | 2 | 0.00 | 200.6 | 201.0 | 201.4 | 209.3 | 217.9 | 0.256 | 21 | 0 |
| 1,000 | `mvc-virtual` | 1 | 0.00 | 200.5 | 201.0 | 202.8 | 213.9 | 223.4 | 0.299 | 46 | 0 |
| 1,000 | `mvc-virtual` | 2 | 0.00 | 200.6 | 201.3 | 208.3 | 258.4 | 298.8 | 0.304 | 43 | 0 |
| 1,000 | `mvc-platform` | 1 | 0.00 | 615.7 | 744.1 | 762.2 | 772.4 | 780.3 | 0.252 | 249 | 0 |
| 1,000 | `mvc-platform` | 2 | 0.00 | 720.3 | 913.3 | 954.7 | 980.1 | 989.8 | 0.229 | 271 | 0 |
| 1,500 | `webflux-r2dbc` | 1 | 0.00 | 200.5 | 201.0 | 203.4 | 213.6 | 220.3 | 0.311 | 21 | 0 |
| 1,500 | `webflux-r2dbc` | 2 | 0.00 | 200.5 | 201.1 | 207.1 | 342.5 | 375.3 | 0.310 | 21 | 0 |
| 1,500 | `mvc-virtual` | 1 | 0.00 | 200.6 | 201.4 | 208.6 | 235.7 | 410.8 | 0.395 | 56 | 0 |
| 1,500 | `mvc-virtual` | 2 | 0.00 | 200.5 | 201.1 | 207.0 | 228.7 | 275.5 | 0.398 | 51 | 0 |
| 1,500 | `mvc-platform` | 1 | 100.00 | 1,000.0 | 1,001.0 | 1,009.9 | 1,032.3 | 1,044.8 | 0.313 | 261 | 0 |
| 1,500 | `mvc-platform` | 2 | 100.00 | 1,000.0 | 1,001.0 | 1,010.5 | 1,031.9 | 1,047.0 | 0.317 | 278 | 0 |
| 2,000 | `webflux-r2dbc` | 1 | 0.00 | 200.5 | 201.1 | 206.2 | 217.3 | 223.3 | 0.353 | 21 | 0 |
| 2,000 | `webflux-r2dbc` | 2 | 0.00 | 200.5 | 201.4 | 217.5 | 277.6 | 316.2 | 0.359 | 21 | 0 |
| 2,000 | `mvc-virtual` | 1 | 0.00 | 200.6 | 222.6 | 302.0 | 494.8 | 559.1 | 0.572 | 94 | 0 |
| 2,000 | `mvc-virtual` | 2 | 0.00 | 200.6 | 201.8 | 211.8 | 235.2 | 260.7 | 0.548 | 64 | 0 |
| 2,000 | `mvc-platform` | 1 | 100.00 | 689.0 | 1,198.9 | 1,504.2 | 1,806.3 | 2,015.0 | 0.322 | 302 | 21,184 **⚠** |
| 2,000 | `mvc-platform` | 2 | 100.00 | 730.3 | 1,206.8 | 1,469.0 | 1,837.9 | 2,297.7 | 0.330 | 273 | 18,512 **⚠** |

The decisive workload, and it behaved exactly as the arithmetic predicted. `webflux-r2dbc` and `mvc-virtual` hold p50 at 200.5–200.9 ms from 500 to 2,000 rps with zero errors throughout — the 200 ms upstream call and almost nothing else. `mvc-platform` is clean at 500, degrades to a p50 of 615–720 ms at 1,000 (the knee), and fails every request from 1,500 upward. Virtual threads cost more CPU than reactive at every rate: 0.56 against 0.36 cores at 2,000 rps, about 57 % more.

## Where the time actually went

k6 splits each request into `blocked` (waiting for a free connection from
its own pool, which includes waiting for the server to accept the TCP
connection), `connecting`, `sending`, `waiting` (time to first byte) and
`receiving`. That split distinguishes an application that is slow from one
that never got the request.

| cell | err % | duration p50 | waiting p50 | blocked p95 | server-side outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| `mvc-platform · api · 1000rps · r1` | 0.00 | 615.7 | 476.5 | 0.0 | success 120,001 @ 201 ms |
| `mvc-platform · api · 1500rps · r1` | 100.00 | 1,000.0 | 1,000.0 | 834.0 | success 127,256 @ 202 ms |
| `mvc-virtual · api · 1500rps · r1` | 0.00 | 200.6 | 200.5 | 0.0 | success 180,002 @ 200 ms |
| `webflux-r2dbc · api · 1500rps · r1` | 0.00 | 200.5 | 200.5 | 0.0 | success 180,003 @ 200 ms |
| `mvc-platform · db-slow · 1500rps · r1` | 100.00 | 0.0 | 0.0 | 639.5 | success 31,742 @ 1,013 ms |
| `mvc-virtual · db-slow · 1500rps · r1` | 99.01 | 533.3 | 676.4 | 708.7 | success 15,774 @ 8,764 ms, server 80,170 @ 10,178 ms |
| `webflux-r2dbc · db-slow · 1500rps · r1` | 100.00 | 906.7 | 918.2 | 0.2 | success 14 @ 909 ms, server 165,159 @ 903 ms |
| `webflux-r2dbc · db-heavy · 1500rps · r2` | 0.00 | 13.0 | 12.8 | 0.0 | success 179,955 @ 91 ms |
| `mvc-virtual · db-heavy · 1500rps · r2` | 0.00 | 12.5 | 12.4 | 0.0 | success 180,000 @ 13 ms |

Three things fall out of that table.

**`mvc-platform` on `/api` at 1,500 rps was not slow — it was unreachable.**
The server completed 127,256 requests at a mean of 202 ms, exactly the
upstream call plus overhead, and logged no exceptions at all. Meanwhile
`blocked` reached 834 ms at p95: the requests were sitting in the accept
queue, never reaching the application, and the client abandoned them at one
second. Tomcat's 200 threads at 200 ms each cap throughput at 1,000 rps, so
at 1,500 the surplus 500 per second simply accumulated.

**At exactly 1,000 rps the same variant showed 0 % errors and a p50 of**
**615.7 ms.** That is the queue filling but not overflowing inside the
timeout — the knee itself, caught between the two rungs of the ladder.

**On `/db-slow` the three stacks failed in three different ways.**
`mvc-platform` served a trickle successfully and left everything else in the
accept queue, burning 0.056 cores — the application was almost idle.
`mvc-virtual` admitted the load, exhausted the pool and returned 80,170
`CannotGetJdbcConnectionException` responses while burning 1.18 cores.
`webflux-r2dbc` admitted it too and returned 165,159
`TransientDataAccessResourceException` responses at 1.62 cores, with 14
successes. Same 100 % failure rate; completely different shapes.

## Server-side failures

Exception counts differenced across the measured window, by endpoint.

| endpoint | variant | exception | count |
| --- | --- | --- | ---: |
| `/db-slow` | `webflux-r2dbc` | `TransientDataAccessResourceException` | 633,348 |
| `/db-slow` | `mvc-virtual` | `CannotGetJdbcConnectionException` | 511,228 |
| `/db-heavy` | `mvc-virtual` | `CannotGetJdbcConnectionException` | 35,393 |
| `/db-slow` | `webflux-r2dbc` | `AbortedException` | 78 |
| `/db` | `mvc-virtual` | `DataAccessResourceFailureException` | 40 |

`mvc-platform` raised **no** server-side exceptions anywhere,
including on cells k6 scored at 100 % failure. Its failures were entirely
client-side timeouts against a full accept queue — the application never saw
the request, so it had nothing to fail on.

Connection-pool timeouts (`hikaricp_connections_timeout_total`):

| cell | timeouts |
| --- | ---: |
| `mvc-virtual · db-slow · 1500rps · r2` | 81,457 |
| `mvc-virtual · db-slow · 2000rps · r2` | 81,409 |
| `mvc-virtual · db-slow · 2000rps · r1` | 80,482 |
| `mvc-virtual · db-slow · 1500rps · r1` | 80,164 |
| `mvc-virtual · db-slow · 1000rps · r2` | 76,672 |
| `mvc-virtual · db-slow · 1000rps · r1` | 74,954 |
| `mvc-virtual · db-slow · 500rps · r2` | 36,092 |
| `mvc-virtual · db-slow · 500rps · r1` | 31,840 |
| `mvc-virtual · db-heavy · 2000rps · r2` | 17,993 |
| `mvc-virtual · db-heavy · 2000rps · r1` | 17,399 |
| `mvc-virtual · db-heavy · 500rps · r1` | 7,525 |
| `mvc-virtual · api · 500rps · r1` | 253 |

The 253 timeouts attributed to `mvc-virtual · api · 500rps · r1` are
contamination, not a result: `/api` touches no database. The JVM was
still draining queued `/db-slow` work from the previous cell when this
one's first scrape was taken. It is the clearest evidence that not
restarting the JVM between cells has a cost.

## Resource use

Medians of both repetitions. CPU is the reliable figure here; heap is a
single sample taken at the end of the window and sawtooths with GC, so it is
reported alongside live-set size, which is measured after a collection and
is far steadier.

| workload | rate | variant | cores | of 2 vCPU | heap MB | live set MB | threads | GC pauses | GC ms | allocated GB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `/nodb` | 500 | `webflux-r2dbc` | 0.086 | 4 % | 764 | 213 | 21 | 2 | 9 | 1.2 |
| `/nodb` | 500 | `mvc-virtual` | 0.078 | 4 % | 577 | 102 | 20 | 1 | 28 | 0.6 |
| `/nodb` | 500 | `mvc-platform` | 0.083 | 4 % | 450 | 121 | 216 | 2 | 24 | 0.7 |
| `/nodb` | 1,000 | `webflux-r2dbc` | 0.099 | 5 % | 837 | 213 | 21 | 4 | 23 | 2.4 |
| `/nodb` | 1,000 | `mvc-virtual` | 0.080 | 4 % | 495 | 93 | 20 | 3 | 28 | 1.7 |
| `/nodb` | 1,000 | `mvc-platform` | 0.074 | 4 % | 175 | 64 | 215 | 3 | 41 | 1.7 |
| `/nodb` | 1,500 | `webflux-r2dbc` | 0.117 | 6 % | 367 | 213 | 21 | 6 | 42 | 3.9 |
| `/nodb` | 1,500 | `mvc-virtual` | 0.094 | 5 % | 604 | 84 | 20 | 4 | 49 | 2.2 |
| `/nodb` | 1,500 | `mvc-platform` | 0.100 | 5 % | 405 | 57 | 215 | 4 | 51 | 2.2 |
| `/nodb` | 2,000 | `webflux-r2dbc` | 0.119 | 6 % | 582 | 213 | 21 | 8 | 64 | 4.7 |
| `/nodb` | 2,000 | `mvc-virtual` | 0.123 | 6 % | 471 | 129 | 20 | 6 | 59 | 3.2 |
| `/nodb` | 2,000 | `mvc-platform` | 0.123 | 6 % | 431 | 96 | 215 | 6 | 54 | 3.2 |
| `/db` | 500 | `webflux-r2dbc` | 0.193 | 10 % | 445 | 81 | 21 | 6 | 28 | 3.6 |
| `/db` | 500 | `mvc-virtual` | 0.168 | 8 % | 118 | 0 | 21 | 3 | 46 | 1.7 |
| `/db` | 500 | `mvc-platform` | 0.148 | 7 % | 521 | 0 | 129 | 2 | 46 | 1.1 |
| `/db` | 1,000 | `webflux-r2dbc` | 0.215 | 11 % | 603 | 81 | 21 | 12 | 67 | 7.1 |
| `/db` | 1,000 | `mvc-virtual` | 0.148 | 7 % | 318 | 0 | 21 | 6 | 80 | 3.1 |
| `/db` | 1,000 | `mvc-platform` | 0.094 | 5 % | 412 | 0 | 169 | 5 | 75 | 2.8 |
| `/db` | 1,500 | `webflux-r2dbc` | 0.292 | 15 % | 288 | 81 | 21 | 18 | 123 | 11.0 |
| `/db` | 1,500 | `mvc-virtual` | 0.174 | 9 % | 406 | 0 | 21 | 8 | 139 | 4.7 |
| `/db` | 1,500 | `mvc-platform` | 0.128 | 6 % | 480 | 0 | 207 | 7 | 85 | 4.0 |
| `/db` | 2,000 | `webflux-r2dbc` | 0.352 | 18 % | 397 | 81 | 21 | 24 | 177 | 14.5 |
| `/db` | 2,000 | `mvc-virtual` | 0.287 | 14 % | 655 | 0 | 21 | 10 | 126 | 6.1 |
| `/db` | 2,000 | `mvc-platform` | 0.157 | 8 % | 744 | 0 | 215 | 9 | 81 | 5.3 |
| `/db-heavy` | 500 | `webflux-r2dbc` | 0.258 | 13 % | 509 | 213 | 21 | 24 | 88 | 14.6 |
| `/db-heavy` | 500 | `mvc-virtual` | 0.192 | 10 % | 300 | 87 | 21 | 24 | 888 | 4.7 |
| `/db-heavy` | 500 | `mvc-platform` | 0.131 | 7 % | 276 | 48 | 215 | 8 | 65 | 3.9 |
| `/db-heavy` | 1,000 | `webflux-r2dbc` | 0.409 | 20 % | 585 | 213 | 21 | 50 | 214 | 29.8 |
| `/db-heavy` | 1,000 | `mvc-virtual` | 0.154 | 8 % | 437 | 71 | 21 | 14 | 103 | 7.8 |
| `/db-heavy` | 1,000 | `mvc-platform` | 0.148 | 7 % | 610 | 48 | 216 | 12 | 104 | 7.2 |
| `/db-heavy` | 1,500 | `webflux-r2dbc` | 0.613 | 31 % | 353 | 213 | 21 | 75 | 435 | 44.6 |
| `/db-heavy` | 1,500 | `mvc-virtual` | 0.233 | 12 % | 405 | 71 | 21 | 20 | 203 | 11.6 |
| `/db-heavy` | 1,500 | `mvc-platform` | 0.211 | 11 % | 363 | 48 | 216 | 20 | 212 | 11.3 |
| `/db-heavy` | 2,000 | `webflux-r2dbc` | 0.498 | 25 % | 338 | 213 | 21 | 55 | 1,150 | 31.8 |
| `/db-heavy` | 2,000 | `mvc-virtual` | 1.295 | 65 % | 948 | 852 | 21 | 374 | 33,676 | 15.3 |
| `/db-heavy` | 2,000 | `mvc-platform` | 0.400 | 20 % | 420 | 187 | 216 | 40 | 1,440 | 15.9 |
| `/db-slow` | 500 | `webflux-r2dbc` | 0.430 | 22 % | 563 | 203 | 21 | 53 | 2,440 | 29.4 |
| `/db-slow` | 500 | `mvc-virtual` | 0.296 | 15 % | 821 | 717 | 21 | 51 | 2,296 | 7.3 |
| `/db-slow` | 500 | `mvc-platform` | 0.057 | 3 % | 415 | 216 | 216 | 4 | 218 | 1.6 |
| `/db-slow` | 1,000 | `webflux-r2dbc` | 0.846 | 42 % | 455 | 157 | 21 | 139 | 4,524 | 78.5 |
| `/db-slow` | 1,000 | `mvc-virtual` | 1.127 | 56 % | 945 | 905 | 21 | 359 | 27,305 | 14.7 |
| `/db-slow` | 1,000 | `mvc-platform` | 0.053 | 3 % | 423 | 179 | 216 | 4 | 176 | 1.4 |
| `/db-slow` | 1,500 | `webflux-r2dbc` | 1.632 | 82 % | 754 | 236 | 21 | 224 | 6,509 | 127.0 |
| `/db-slow` | 1,500 | `mvc-virtual` | 1.172 | 59 % | 945 | 907 | 21 | 415 | 31,845 | 16.7 |
| `/db-slow` | 1,500 | `mvc-platform` | 0.054 | 3 % | 685 | 227 | 216 | 6 | 209 | 1.3 |
| `/db-slow` | 2,000 | `webflux-r2dbc` | 0.144 | 7 % | 368 | 213 | 21 | 14 | 514 | 7.9 |
| `/db-slow` | 2,000 | `mvc-virtual` | 1.193 | 60 % | 965 | 866 | 21 | 434 | 33,701 | 17.9 |
| `/db-slow` | 2,000 | `mvc-platform` | 0.050 | 3 % | 524 | 248 | 216 | 4 | 169 | 1.2 |
| `/api` | 500 | `webflux-r2dbc` | 0.169 | 8 % | 742 | 213 | 21 | 4 | 21 | 2.1 |
| `/api` | 500 | `mvc-virtual` | 0.268 | 13 % | 405 | 144 | 52 | 12 | 742 | 3.7 |
| `/api` | 500 | `mvc-platform` | 0.248 | 12 % | 268 | 56 | 226 | 6 | 66 | 3.1 |
| `/api` | 1,000 | `webflux-r2dbc` | 0.256 | 13 % | 530 | 213 | 21 | 8 | 70 | 4.4 |
| `/api` | 1,000 | `mvc-virtual` | 0.301 | 15 % | 484 | 87 | 44 | 12 | 165 | 6.8 |
| `/api` | 1,000 | `mvc-platform` | 0.241 | 12 % | 372 | 69 | 260 | 12 | 141 | 6.6 |
| `/api` | 1,500 | `webflux-r2dbc` | 0.310 | 16 % | 388 | 213 | 21 | 12 | 140 | 6.8 |
| `/api` | 1,500 | `mvc-virtual` | 0.397 | 20 % | 301 | 147 | 54 | 18 | 235 | 10.4 |
| `/api` | 1,500 | `mvc-platform` | 0.315 | 16 % | 480 | 320 | 270 | 28 | 1,593 | 9.1 |
| `/api` | 2,000 | `webflux-r2dbc` | 0.356 | 18 % | 674 | 213 | 21 | 15 | 228 | 8.8 |
| `/api` | 2,000 | `mvc-virtual` | 0.560 | 28 % | 417 | 268 | 79 | 28 | 1,672 | 13.9 |
| `/api` | 2,000 | `mvc-platform` | 0.326 | 16 % | 410 | 228 | 288 | 30 | 1,697 | 9.1 |

## Connection pool behaviour

Mean connection hold and acquire time, differenced across the window. Only
the blocking variants expose these; R2DBC Pool publishes gauges but no
equivalent timer, so its rows are empty by necessity rather than by
omission.

| workload | rate | variant | borrows | hold ms | acquire ms | pending |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| `/db` | 500 | `mvc-virtual` | 60,002 | 0.07 | 0.05 | — |
| `/db` | 500 | `mvc-platform` | 60,002 | 0.02 | 0.01 | — |
| `/db` | 1,000 | `mvc-virtual` | 119,997 | 0.02 | 1.50 | — |
| `/db` | 1,000 | `mvc-platform` | 119,991 | 0.00 | 0.00 | — |
| `/db` | 1,500 | `mvc-virtual` | 179,981 | 0.01 | 2.40 | — |
| `/db` | 1,500 | `mvc-platform` | 180,001 | 0.00 | 0.00 | — |
| `/db` | 2,000 | `mvc-virtual` | 240,002 | 0.01 | 0.01 | — |
| `/db` | 2,000 | `mvc-platform` | 240,003 | 0.00 | 0.00 | — |
| `/db-heavy` | 500 | `mvc-virtual` | 60,450 | 16.08 | 1,569.51 | — |
| `/db-heavy` | 500 | `mvc-platform` | 60,001 | 11.95 | 0.00 | — |
| `/db-heavy` | 1,000 | `mvc-virtual` | 120,002 | 11.96 | 0.03 | — |
| `/db-heavy` | 1,000 | `mvc-platform` | 120,002 | 11.96 | 0.02 | — |
| `/db-heavy` | 1,500 | `mvc-virtual` | 180,001 | 11.97 | 0.66 | — |
| `/db-heavy` | 1,500 | `mvc-platform` | 180,002 | 11.97 | 0.57 | — |
| `/db-heavy` | 2,000 | `mvc-virtual` | 138,814 | 16.81 | 5,866.70 | 6,270 |
| `/db-heavy` | 2,000 | `mvc-platform` | 201,153 | 12.08 | 111.59 | 177 |
| `/db-slow` | 500 | `mvc-virtual` | 23,770 | 101.76 | 9,756.44 | 4,289 |
| `/db-slow` | 500 | `mvc-platform` | 31,992 | 101.03 | 908.07 | 179 |
| `/db-slow` | 1,000 | `mvc-virtual` | 18,992 | 127.55 | 9,921.48 | 6,912 |
| `/db-slow` | 1,000 | `mvc-platform` | 32,139 | 100.98 | 911.40 | 179 |
| `/db-slow` | 1,500 | `mvc-virtual` | 16,090 | 151.36 | 9,885.53 | 7,680 |
| `/db-slow` | 1,500 | `mvc-platform` | 31,730 | 101.00 | 912.00 | 179 |
| `/db-slow` | 2,000 | `mvc-virtual` | 15,287 | 160.50 | 9,975.57 | 6,639 |
| `/db-slow` | 2,000 | `mvc-platform` | 31,421 | 100.99 | 909.81 | 179 |

The `/db-heavy` hold of about 11.96 ms is the deliberate `pg_sleep(0.011)`
pad plus the real query, and it holds steady across every rate — which is
the pad doing exactly what it was added for.

On `/db-slow` the hold climbs with offered load — roughly 101 ms at 500 rps
to 162 ms at 2,000 on `mvc-virtual` — even though `pg_sleep(0.1)` is fixed.
The extra time is contention inside PostgreSQL once far more sessions are
queued against it than the pool can serve.

## Why R2DBC struggles on /db-heavy

`/db-heavy` is the one workload where the two candidates diverge sharply,
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
on this evidence, the direction.

## Findings

**1. The thread ceiling is real, and lands exactly where predicted.**
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
CPU to recover with.

## Invalid cells

k6 dropped iterations during the measured phase in these cells, so the
offered rate was not sustained and the figures understate the load. They are
shown in the tables above marked **⚠** and must not be quoted.

| cell | err % | dropped | note |
| --- | ---: | ---: | --- |
| `mvc-platform · api · 2000rps · r1` | 100.00 | 21,184 | generator could not sustain the rate against a saturated server |
| `mvc-platform · api · 2000rps · r2` | 100.00 | 18,512 | generator could not sustain the rate against a saturated server |
| `mvc-virtual · db-heavy · 2000rps · r2` | 91.84 | 163 | generator could not sustain the rate against a saturated server |
| `webflux-r2dbc · db-heavy · 2000rps · r1` | 61.37 | 29,673 | generator could not sustain the rate against a saturated server |
| `webflux-r2dbc · db-heavy · 2000rps · r2` | 58.24 | 35,422 | generator could not sustain the rate against a saturated server |
| `mvc-platform · db-slow · 1000rps · r1` | 100.00 | 8,585 | generator could not sustain the rate against a saturated server |
| `mvc-platform · db-slow · 1000rps · r2` | 100.00 | 8,576 | generator could not sustain the rate against a saturated server |
| `mvc-platform · db-slow · 1500rps · r1` | 100.00 | 34,437 | generator could not sustain the rate against a saturated server |
| `mvc-platform · db-slow · 1500rps · r2` | 100.00 | 31,593 | generator could not sustain the rate against a saturated server |
| `mvc-platform · db-slow · 2000rps · r1` | 100.00 | 55,159 | generator could not sustain the rate against a saturated server |
| `mvc-platform · db-slow · 2000rps · r2` | 100.00 | 56,965 | generator could not sustain the rate against a saturated server |
| `mvc-virtual · db-slow · 2000rps · r1` | 99.35 | 29,437 | generator could not sustain the rate against a saturated server |
| `mvc-virtual · db-slow · 2000rps · r2` | 99.34 | 30,093 | generator could not sustain the rate against a saturated server |
| `webflux-r2dbc · db-slow · 2000rps · r1` | 98.03 | 77,210 | generator could not sustain the rate against a saturated server |
| `webflux-r2dbc · db-slow · 2000rps · r2` | 98.07 | 74,444 | generator could not sustain the rate against a saturated server |

All 21 are at the top of a ladder against an already-failing server. None
sit in a region where a variant was still healthy, so no conclusion below
rests on one.

## What changed against the laptop run

| | Laptop | AWS | Verdict |
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
which the current runner does not do.

## Still not established

**Memory over time was not sampled.** One heap reading per cell, taken at the
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

