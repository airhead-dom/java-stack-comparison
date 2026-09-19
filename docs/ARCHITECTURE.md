# Benchmark architecture on EC2

## Why not one box

Every number this benchmark produces is a statement about how the application
behaves under a given CPU budget. If the load generator, the application, the
stub and Postgres share a machine, they compete, and the measurement becomes a
statement about the machine instead. Local runs proved this: the same cell gave
p99 205ms and p99 1,264ms on different attempts.

So the system under test gets CPUs nobody else touches, and everything that
could steal from it is moved off.

## Topology

```
                         VPC 10.0.0.0/16
                  single AZ, cluster placement group
   ┌───────────────────────────────────────────────────────────────┐
   │                                                               │
   │   ┌─────────────────────┐                                     │
   │   │  load-generator     │                                     │
   │   │  m7i.xlarge         │                                     │
   │   │  4 vCPU / 16 GB     │                                     │
   │   │                     │                                     │
   │   │  k6                 │   offered load, open model          │
   │   │  results/raw/       │   up to 2,900 VUs                   │
   │   └──────────┬──────────┘                                     │
   │              │                                                │
   │              │  HTTP :8080        ← the only traffic that     │
   │              │                      must not be contended     │
   │              ▼                                                │
   │   ┌─────────────────────┐                                     │
   │   │  sut  ★             │   ★ the experimental constant:      │
   │   │  c7i.large          │     identical CPU, RAM, JVM flags   │
   │   │  2 vCPU / 4 GB      │     for every variant               │
   │   │                     │                                     │
   │   │  one variant at a   │   mvc-platform | mvc-virtual        │
   │   │  time, port 8080    │   webflux-r2dbc | mvc-jpa           │
   │   └─────┬────────┬──────┘                                     │
   │         │        │                                            │
   │  :5432  │        │  :9099                                     │
   │         ▼        ▼                                            │
   │   ┌─────────────────────┐                                     │
   │   │  backend            │                                     │
   │   │  m7i.large          │                                     │
   │   │  2 vCPU / 8 GB      │                                     │
   │   │                     │                                     │
   │   │  postgres 17        │  shared_buffers 2GB                 │
   │   │  stub-service       │  200ms delayed responses            │
   │   └─────────────────────┘                                     │
   │                                                               │
   └───────────────────────────────────────────────────────────────┘
             SSH :22 from your IP only, all three boxes
```

## Why Postgres and the stub share a box

They are never busy at the same time:

| Workload | Postgres | stub-service |
| --- | --- | --- |
| `nodb` | idle | idle |
| `db`, `db-heavy`, `db-slow` | **busy** | idle |
| `api` | idle | **busy** |

`/api` touches no database, and the database workloads make no upstream call.
Each one has the box to itself, so co-locating them costs nothing and saves an
instance.

The constraint this creates: **never run a mixed workload.** If a future
scenario combines a query and an upstream call in one request, the stub moves to
its own `t3.small` first.

## Instance sizing, and why

| Role | Type | vCPU | RAM | Reason |
| --- | --- | --- | --- | --- |
| load-generator | `m7i.xlarge` | 4 | 16 GB | VU memory. Full pre-allocation at 2,400 rps needs ~2,900 VUs at roughly 2 MB each, so ~6 GB for VUs alone, plus headroom. Memory is the binding constraint here, not CPU — hence `m7i` rather than `c7i`. |
| sut | `c7i.large` | 2 | 4 GB | Small on purpose. The thread model only matters when a resource is scarce; a large box would hide the effect. Compute-optimised so CPU is the clean constraint. |
| backend | `m7i.large` | 2 | 8 GB | The seeded dataset is ~870 MB and must sit in `shared_buffers` (2 GB) or the benchmark measures EBS. |

**Not burstable.** No `t3`/`t4g`, and no Lightsail. Burstable instances throttle
hard once CPU credits run out, mid-run, with no error — and because variants run
sequentially, the throttling would correlate with whichever variant happened to
be running. That is the worst kind of confound: invisible and systematic.

**x86, not Graviton.** `c7g` is cheaper, but production is almost certainly x86
and there is no reason to introduce an architecture difference into a study
about thread models.

## Network

- **One VPC, one subnet, one AZ.** Cross-AZ adds ~0.5–1ms of latency with real
  variance. Availability is irrelevant here; consistency is everything.
- **Cluster placement group.** Packs the instances onto nearby hardware for low,
  consistent inter-instance latency. Free, and it removes a source of noise.
- **One security group, self-referencing**, so the three instances talk freely
  on any port. Plus SSH from your IP only.
- Public subnet with public IPs, rather than private subnet plus NAT gateway.
  A NAT gateway costs more than all three instances combined and buys nothing
  for a temporary benchmark.

Expect ~0.2–0.5ms round trip between instances. That matters: it is added to
every database call, and it is part of why production reports 15ms while a local
Postgres reports 1ms.

## Software

| | |
| --- | --- |
| OS | Ubuntu 24.04 LTS |
| JDK | Temurin 25.0.4, same build on every box |
| Postgres | 17, via Docker, `shared_buffers=2GB` |
| k6 | v2.2.0, matching local |

Deployment is `scp` of the jars built locally, then `java -jar`. No CI, no
containers for the variants — fewer layers between the code and the measurement.

**Disable unattended upgrades before any run.** A background `apt` job waking up
mid-cell will steal CPU from the SUT and silently ruin that cell.

## Observability

No Prometheus server initially. Each run snapshots the scrape endpoint before
and after, exactly as the local flow does:

```bash
curl -s http://SUT:8080/actuator/prometheus > results/raw/<tag>.metrics.before.txt
```

Counters get differenced at analysis time. This avoids running a Prometheus
server that would itself need a home and a CPU budget.

Grafana is worth adding later, on the load-generator box, once there are enough
runs to know which panels matter.

## Cost

Roughly **$0.40/hour** for all three in `us-east-1`, so a full matrix of about
9 hours lands near **$4**, plus a few cents of EBS. Verify current pricing in
your region — Jakarta (`ap-southeast-3`) runs meaningfully higher than
`us-east-1`.

Stop the instances between sessions. Stopped instances bill only for EBS.

## What stays constant across every run

This list is the experiment. Anything on it that drifts invalidates a
comparison.

- Instance types and sizes
- `-Xms1g -Xmx1g -XX:+UseG1GC` on the SUT
- `POOL_SIZE=20`, applied to Hikari and R2DBC alike
- `UPSTREAM_DELAY_MS=200`
- The seeded dataset, restored from the same volume snapshot
- Placement group and subnet
- k6 version and scenario files
