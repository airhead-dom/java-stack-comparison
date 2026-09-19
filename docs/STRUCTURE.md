# Repository layout

| Path | Purpose |
| --- | --- |
| `buildSrc/` | `benchmark-app` convention plugin: toolchain, actuator, Prometheus, JVM flags. Applied by every variant so instrumentation cannot drift between them. |
| `common/` | Domain records and SQL only. No web layer, no persistence layer -- sharing either would couple the layer under test. |
| `mvc-platform/` | Spring MVC, platform threads, `JdbcClient`. Baseline. |
| `mvc-virtual/` | Identical to `mvc-platform` except `spring.threads.virtual.enabled: true`. |
| `mvc-jpa/` | Control. Isolates Hibernate's cost with the thread model held fixed against `mvc-platform`. |
| `webflux-r2dbc/` | WebFlux end to end, `DatabaseClient`. |
| `webflux-jdbc/` | WebFlux with blocking JDBC on `boundedElastic`. |
| `stub-service/` | Fake upstream with injectable latency for the `/composite` workload. |
| `infra/` | `docker-compose.yml` for local dev; `terraform/` for the 3-instance EC2 setup. |
| `load/` | k6 scenarios plus the run matrix. |
| `scripts/` | Run orchestration and result collection. |
| `results/raw/` | Immutable per-run output. Never edited. |
| `results/analysis/` | Everything derived from `raw/`, regenerable. |

## What is being compared

Five variants of the same API. Each differs from the baseline in exactly one
respect; if two things differ at once, the comparison means nothing.

| Variant | The one thing that differs |
| --- | --- |
| `mvc-platform` | -- (baseline) |
| `mvc-virtual` | virtual threads instead of platform threads |
| `webflux-r2dbc` | reactive web layer and reactive driver |
| `webflux-jdbc` | reactive web layer, blocking driver offloaded |
| `mvc-jpa` | Hibernate instead of `JdbcClient` |

## Invariants

- All variants listen on **8080** so load scripts never change between runs.
- Pool size is set by `POOL_SIZE` (default 10) and is identical everywhere,
  including R2DBC's `max-size`.
- Heap, GC and JFR settings live only in the convention plugin.
- Every variant reports a `variant` Micrometer tag, so Prometheus series can be
  told apart without relying on which process happened to be running.
- `spring-boot-devtools` is deliberately absent: its restart classloader and
  disabled caches would distort every measurement.
