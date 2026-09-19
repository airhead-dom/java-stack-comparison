# Workload design and sizing

Derived from the agreed targets: **1,000 RPS per instance**, **15ms of database
connection hold time per request**, **500ms latency budget**.

## Pool sizing

```
connections needed = RPS x connection_hold_time
                   = 1,000 x 0.015s
                   = 15 connections at 100% utilisation
```

Running a pool at 100% utilisation guarantees an unbounded queue -- waiting time
grows without limit as utilisation approaches 1. `POOL_SIZE` is therefore **20**,
which puts the target load at 75% utilisation and places pool saturation at:

```
20 / 0.015s = 1,333 RPS
```

That number is the designed knee. The rate ladder straddles it on purpose.

## The problem with the obvious test

Little's Law also gives the number of requests in flight:

```
in flight = RPS x latency
          = 1,000 x 0.015s
          = 15 concurrent requests
```

**Fifteen.** Tomcat's default pool is 200 platform threads. At the target load on
a plain database read, the thread model is invisible -- every variant has ample
threads and they will all return the same numbers. A benchmark built only on
this endpoint answers nothing.

The thread model becomes visible only when in-flight count is large, which needs
either high latency per request or load past saturation. The workloads below are
chosen to produce both.

## Workloads

| Endpoint | Work | Conn. hold | Latency | In flight @1k RPS |
| --- | --- | --- | --- | --- |
| `/nodb` | constant response | 0ms | ~1ms | ~1 |
| `/fast` | account summary read | ~15ms | ~15ms | ~15 |
| `/slow` | read + `pg_sleep(0.1)` | ~100ms | ~100ms | ~100 |
| `/composite` | read, release, then 200ms upstream call | ~15ms | ~215ms | **~215** |

`/composite` is the decisive one. It holds a connection only briefly, so the
pool is nowhere near its limit, but each request occupies a *thread* for 215ms.
At 1,000 RPS that is ~215 concurrent requests -- just past Tomcat's 200-thread
default. `mvc-platform` starts queueing at the thread pool while `mvc-virtual`
and `webflux-r2dbc` do not, and no arithmetic about connection pools explains
the gap. This is the shape of a real banking call that fans out to another
service.

`/slow` saturates the pool at `20 / 0.1 = 200 RPS`, so its ladder is centred far
below 1,000.

## Rate ladders

| Workload | Rates (RPS) | Knee |
| --- | --- | --- |
| `/nodb` | 1,000 / 2,000 / 4,000 / 8,000 | web layer |
| `/fast` | 400 / 800 / 1,000 / 1,200 / 1,600 / 2,400 | 1,333 (pool) |
| `/slow` | 50 / 100 / 150 / 200 / 300 / 400 | 200 (pool) |
| `/composite` | 400 / 800 / 1,000 / 1,400 / 2,000 | 200 (threads) |

Three repetitions per cell, order randomised, containers restarted between runs.

## Calibration owed

The seeded account-summary query measures ~0.2ms locally, not 15ms. Production's
15ms presumably covers several queries plus network. Phase 1 must measure the
real hold time of the realistic query via `hikaricp_connections_usage_seconds`
and then either accept the measured figure or pad it to 15ms deliberately.
Padding is legitimate as long as it is recorded here; silently benchmarking a
0.2ms query while claiming to model a 15ms one is not.
