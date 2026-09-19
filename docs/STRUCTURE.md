# Repository layout

| Path | Purpose |
| --- | --- |
| `buildSrc/` | `benchmark-app` convention plugin: toolchain, actuator, Prometheus, JVM flags. Applied by every arm so instrumentation cannot drift between them. |
| `common/` | Domain records and SQL only. No web layer, no persistence layer -- sharing either would couple the layer under test. |
| `arm-a-mvc-platform/` | Spring MVC, platform threads, `JdbcClient`. Baseline. |
| `arm-b-mvc-virtual/` | Identical to arm A except `spring.threads.virtual.enabled: true`. |
| `arm-a2-mvc-jpa/` | Control arm. Isolates Hibernate's cost with the thread model fixed. |
| `arm-c-webflux-r2dbc/` | WebFlux end to end, `DatabaseClient`. |
| `arm-d-webflux-jdbc/` | WebFlux with blocking JDBC on `boundedElastic`. |
| `stub-service/` | Fake upstream with injectable latency for the `/composite` workload. |
| `infra/` | `docker-compose.yml` for local dev; `terraform/` for the 3-instance EC2 setup. |
| `load/` | k6 scenarios plus the run matrix. |
| `scripts/` | Run orchestration and result collection. |
| `results/raw/` | Immutable per-run output. Never edited. |
| `results/analysis/` | Everything derived from `raw/`, regenerable. |

## Invariants

- All arms listen on **8080** so load scripts never change between runs.
- Pool size is set by `POOL_SIZE` (default 10) and is identical in every arm,
  including R2DBC's `max-size`.
- Heap, GC and JFR settings live only in the convention plugin.
- `spring-boot-devtools` is deliberately absent: its restart classloader and
  disabled caches would distort every measurement.
