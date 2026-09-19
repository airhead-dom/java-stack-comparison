# Workload design and sizing

## Agreed simplifications

- **1 transaction = 1 HTTP request.** Internal fan-out is cost, not count.
- **1 transaction does either one database operation or one downstream API
  call**, never both. Keeps each workload attributable to a single cause.
- Target **1,000 TPS**, **15ms** database connection hold time, **500ms**
  latency budget.

Load is generated and recorded in RPS because that is what k6 emits; at 1:1 the
conversion to TPS is the identity, so results can be reported either way.

## Pool sizing

```
connections = TPS x hold_time = 1,000 x 0.015s = 15 at 100% utilisation
```

A pool run at 100% utilisation queues without bound, so `POOL_SIZE` is **20**
(75% utilisation at target). Pool saturation therefore sits at:

```
20 / 0.015s = 1,333 TPS
```

## Why one endpoint is not enough

```
in flight = TPS x latency = 1,000 x 0.015s = 15 concurrent requests
```

Fifteen, against Tomcat's 200 default threads. On a plain database read the
thread model is invisible and all four variants return the same numbers. The
thread model only shows up when requests are in flight for a long time, which is
what `/api` is for.

## Workloads

| Endpoint | Work | Hold | Latency | In flight @1k TPS | Knee |
| --- | --- | --- | --- | --- | --- |
| `/nodb` | constant response | -- | ~1ms | ~1 | web layer |
| `/db` | one account-summary query | 15ms | ~15ms | ~15 | 1,333 (pool) |
| `/db-slow` | one query, `pg_sleep(0.1)` | 100ms | ~100ms | ~100 | 200 (pool) |
| `/api` | one 200ms downstream call | -- | ~200ms | **~200** | 1,000 (threads) |

`/api` is the decisive workload. It touches no database, so the connection pool
cannot explain anything that happens; each request simply occupies a thread for
200ms. At 1,000 TPS that is ~200 concurrent requests, exactly Tomcat's default
thread count. `mvc-platform` begins queueing there while `mvc-virtual` and
`webflux-r2dbc` do not.

`/db` and `/db-slow` are pool-bound and should look near-identical across
variants. That is a result, not a failure -- it is the evidence that the thread
model does not matter for plain database work at this load.

## Rate ladders

| Workload | Rates (TPS) |
| --- | --- |
| `/nodb` | 1,000 / 2,000 / 4,000 / 8,000 |
| `/db` | 400 / 800 / 1,000 / 1,200 / 1,600 / 2,400 |
| `/db-slow` | 50 / 100 / 150 / 200 / 300 / 400 |
| `/api` | 250 / 500 / 1,000 / 1,500 / 2,000 |

Three repetitions per cell, order randomised, containers restarted between runs.

## Calibration owed

The seeded account-summary query measures ~0.2ms locally, not 15ms. Phase 1 must
measure real hold time via `hikaricp_connections_usage_seconds` and then either
accept the measured value or pad `/db` to 15ms deliberately. Padding is fine if
recorded here; benchmarking a 0.2ms query while claiming to model 15ms is not.

## Deliberately out of scope

Multi-call transactions, parallel fan-out, and transactions spanning both a
database operation and a downstream call. Each would be worth measuring, and
each would make a difference impossible to attribute to one cause.
