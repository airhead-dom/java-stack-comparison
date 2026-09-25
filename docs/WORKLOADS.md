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
| `/db` | one account-summary query | 1.0ms | ~2ms | ~2 | not pool-bound |
| `/db-heavy` | statement query, padded to production hold time | 14.4ms | ~15ms | ~15 | 1,387 (pool) |
| `/db-slow` | one query, `pg_sleep(0.1)` | 100ms | ~100ms | ~100 | 200 (pool) |
| `/api` | one 200ms downstream call | -- | ~200ms | **~200** | 1,000 (threads) |
| `/api-800` | one 800ms downstream call | -- | ~810ms | **~800** | no thread knee |
| `/api-1000` | one 1,000ms downstream call | -- | ~1,010ms | **~1,000** | no thread knee |

`/api` is the decisive workload. It touches no database, so the connection pool
cannot explain anything that happens; each request simply occupies a thread for
200ms. At 1,000 TPS that is ~200 concurrent requests, exactly Tomcat's default
thread count. `mvc-platform` begins queueing there while `mvc-virtual` and
`webflux-r2dbc` do not.

`/db` and `/db-slow` are pool-bound and should look near-identical across
variants. That is a result, not a failure -- it is the evidence that the thread
model does not matter for plain database work at this load.

## Rate ladders

One ladder for every workload: **500 / 1,000 / 1,500 / 2,000 TPS**, two
repetitions per cell. A single ladder makes the variants directly comparable at
the same offered rate, and straddles the 1,000 TPS target on both sides.

The knees fall at different places on it:

| Workload | Binds at | Position on the ladder |
| --- | --- | --- |
| `/nodb` | web layer, far above | never binds; a control |
| `/db` | ~19,900 (pool) | never binds |
| `/db-heavy` | ~1,387 (pool) | between 1,000 and 1,500 |
| `/db-slow` | ~200 (pool) | **below the whole ladder** |
| `/api` | ~1,000 (threads) | at the second rung |
| `/api-800` | nothing, for the two candidates | never binds |
| `/api-1000` | nothing, for the two candidates | never binds |

`/db-slow` is saturated at every rate here. Its pool serves 200 TPS and the
lowest rung offers 500, so expect queueing and timeouts in every cell, identical
across variants. That is a property of the pool, not of the thread model. To get
anything else from it, either run it on its own low ladder
(`./run-db-slow.sh "50 100 150 200 300"`) or raise `POOL_SIZE` for those runs.

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

### The pad, and exactly what it is

`/db-heavy` carries a deliberate `pg_sleep(0.011)` so that it holds a connection
for the production-reported 15ms. Measured after tuning: **14.42ms** over 300
warm borrows, putting pool saturation at **1,387 TPS** -- within 4% of the 1,333
the rate ladder was designed around.

The sleep value is 11ms, not 14ms, because `pg_sleep` carries several
milliseconds of its own overhead; 14ms produced an 18ms hold. The figure was
tuned empirically against the measured metric, not calculated.

What the pad does and does not model:

- **Does**: connection occupancy, and therefore pool queueing, saturation and
  the shape of overload. This is what the rate ladder tests.
- **Does not**: CPU, I/O or memory pressure. A sleeping connection burns none of
  them. Any claim about database *throughput* from this endpoint would be wrong.

It stands in for network latency to a remote database and for contention on a
busy production instance, neither of which a local or same-AZ Postgres
reproduces.

`/db` is left deliberately unpadded at 1.0ms, so the two endpoints bracket the
range: one shows the cheap-query case where the pool never binds, the other the
production-realistic case where it does.

Hibernate measurably costs more inside the connection window: `mvc-jpa` held
connections 1.93ms on `/db-heavy` against 1.21ms for `mvc-platform` on the same
query -- roughly 60% longer -- on a first, unrepeated sample.

### Observability asymmetry

R2DBC pool gauges are exported by Spring Boot as `r2dbc_pool_*_connections`, so
`pending`, `idle` and `acquired` are comparable across variants. There is no
R2DBC equivalent of Hikari's `connections_usage_seconds` timer, so mean hold
time cannot be read directly from `webflux-r2dbc` and must be inferred from
latency.

## The long-wait workloads: `/api-800` and `/api-1000`

`/api` was sized so that in-flight concurrency lands exactly on Tomcat's 200
threads. That made it decisive about `mvc-platform`, and that question is now
answered. These two ask a different one.

At an 800ms or 1,000ms delay the same rate ladder puts far more requests in
flight, and past any thread count either candidate has:

| | in flight @500 | @1,000 | @1,500 | @2,000 |
| --- | ---: | ---: | ---: | ---: |
| `/api` | 100 | 200 | 300 | 400 |
| `/api-800` | 400 | 800 | 1,200 | 1,600 |
| `/api-1000` | 500 | 1,000 | 1,500 | 2,000 |

At a one-second delay the offered rate and the in-flight count are the same
number, which is what makes that endpoint worth having beside the 800ms one:
two points on a line rather than one measurement to be interpreted.

**Neither stack has a knee here, and that is the point.** Nothing about a thread
count binds for `mvc-virtual` or `webflux-r2dbc` at these rates, so what these
cells measure is the *cost of holding a request that is waiting* -- heap, CPU
and sockets against in-flight count -- rather than where throughput stops.
Expect a curve, not a cliff.

### Only two variants

`mvc-platform` and `mvc-jpa` do not implement these endpoints. 200 Tomcat
threads over an 800ms hold cap `mvc-platform` at

```
200 / 0.8s = 250 TPS
```

which is below the bottom rung of the ladder, so every cell would be the same
saturation result already established by `/api` at 1,500 rps. The runners check
the endpoint answers 200 before starting, rather than recording 404s as data.

### What had to change to measure it

- **The generator is the binding constraint, not the SUT.** k6 needs roughly one
  VU per request in flight, and the default 4x pre-allocation margin -- tuned
  when healthy concurrency was ~15 -- would ask for 8,080 VUs at 2,000 rps, about
  16GB. These scenarios pass `vuMargin: 1.3`, and the runners refuse a cell that
  does not fit in the generator's memory rather than dropping iterations and
  calling it a result.
- **Timeouts.** The shared 1,000ms default is *below* `/api-1000`'s healthy
  latency and would fail every request. The two scenarios set 2,000ms and
  2,500ms, with the SLA at delay + 300ms to match `/api`'s 200 + 300.
- **Sampling during the run.** The before/after scrape pair every other workload
  uses is taken while the system is idle, so a gauge reads 0 in-flight and
  whatever GC left behind for heap. These runners sample the SUT every 2s for
  the whole cell into `$tag.samples.csv`, which is the only way the in-flight
  question gets answered -- and it also gives heap a distribution instead of the
  single unusable point the AWS run had to report.
- **File descriptors and connection caps.** One upstream socket per request in
  flight, for the whole delay. Ubuntu's 1,024 default and the reactive client's
  previous fixed 2,000-connection cap would both have bound at the top rung, and
  either would have looked like a property of the thread model.

Measured in-flight comes from Micrometer's active-request timer. It publishes a
single series labelled `uri="UNKNOWN"` whatever the endpoint -- an in-flight
request has no resolved uri or outcome yet -- so it cannot be split per
endpoint. A cell runs one workload, so the total, less one for the scrape
itself, is that workload's in-flight count.

## Deliberately out of scope

Multi-call transactions, parallel fan-out, and transactions spanning both a
database operation and a downstream call. Each would be worth measuring, and
each would make a difference impossible to attribute to one cause.
