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
| `/db` | one account-summary query | ~1.0ms | ~15ms | ~15 | not pool-bound |
| `/db-heavy` | one statement query: aggregate + 20 rows | ~1.0ms | ~15ms | ~15 | not pool-bound |
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

## Calibration: measured, and still short of 15ms

Measured on the seeded database over 300 warm requests each, via
`hikaricp_connections_usage_seconds`:

| Endpoint | Mean connection hold |
| --- | --- |
| `/db` | 1.03ms |
| `/db-heavy` | 1.02ms |

`/db-heavy` does strictly more work -- an aggregate over the account's whole
history, twenty rows returned and mapped, a much larger response body -- yet
holds its connection for the same ~1ms. The extra cost is in the application,
not at the database: twenty index-scanned rows are trivial for Postgres, while
mapping and serialising them is not free for the JVM. That is worth knowing on
its own, and it is why the heavy endpoint does not fix the sizing problem.

At ~1ms of hold time the pool saturates around 20,000 TPS and never binds, so
neither `/db` nor `/db-heavy` is pool-bound as configured. `/db-slow` remains
the only pool-bound workload. Closing the gap to the stated 15ms production hold
time requires a deliberate pad, which is not yet applied.

Hibernate measurably costs more inside the connection window: `mvc-jpa` held
connections 1.93ms on `/db-heavy` against 1.21ms for `mvc-platform` on the same
query -- roughly 60% longer -- on a first, unrepeated sample.

### Observability asymmetry

R2DBC pool gauges are exported by Spring Boot as `r2dbc_pool_*_connections`, so
`pending`, `idle` and `acquired` are comparable across variants. There is no
R2DBC equivalent of Hikari's `connections_usage_seconds` timer, so mean hold
time cannot be read directly from `webflux-r2dbc` and must be inferred from
latency.

## Deliberately out of scope

Multi-call transactions, parallel fan-out, and transactions spanning both a
database operation and a downstream call. Each would be worth measuring, and
each would make a difference impossible to attribute to one cause.
