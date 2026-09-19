# Running the benchmark

All scripts are bash. On Windows run them from **Git Bash**, not PowerShell or cmd.

## One-time setup

**1. Fix `JAVA_HOME`.** It currently points at a path that does not exist, which
makes `./gradlew` fail. In PowerShell, once:

```powershell
[Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Java\jdk-25.0.4", "User")
```

Then close and reopen your terminal. Verify in Git Bash:

```bash
java -version          # expect 25.0.4
```

**2. Make sure k6 is reachable.** It installs to `C:\Program Files\k6\k6.exe`.
If `k6 version` does not work in Git Bash, either reopen the terminal (the
installer adds it to PATH for new shells) or set it explicitly:

```bash
export K6_BIN="/c/Program Files/k6/k6.exe"
```

Every script honours `K6_BIN` and `JAVA_BIN` overrides.

**3. Build the jars.**

```bash
./gradlew bootJar
```

Re-run this after any code change. The run scripts execute jars, not `bootRun`.

## Each session

```bash
scripts/env-up.sh
```

Starts Postgres and waits for it to seed, then starts stub-service on port 9099.
The **first** start seeds 100k customers, 200k accounts and 2.6M transactions
and takes about 2.5 minutes; later starts reuse the volume and are immediate.

At the end of a session:

```bash
scripts/env-down.sh           # stop, keep the seeded database
scripts/env-down.sh --purge   # stop and delete it (next start re-seeds)
```

## Running one cell

```bash
scripts/run-one.sh <variant> <workload> <rate> [repetition]
```

```bash
scripts/run-one.sh mvc-platform api 1000
scripts/run-one.sh webflux-r2dbc db-heavy 1200 2
```

| Argument | Values |
| --- | --- |
| variant | `mvc-platform` `mvc-virtual` `webflux-r2dbc` `mvc-jpa` |
| workload | `nodb` `db` `db-heavy` `db-slow` `api` |
| rate | requests per second to **offer** |
| repetition | run number, only used to name the output files |

The script starts the variant's JVM, waits for health, runs a warmup that is
discarded, measures, then shuts the JVM down. One variant at a time -- they all
bind port 8080 deliberately, so the load scripts never change between runs.

Useful overrides:

```bash
DURATION=120s WARMUP=60s scripts/run-one.sh mvc-virtual api 1000
UPSTREAM_DELAY_MS=500 scripts/run-one.sh mvc-platform api 1000   # slower upstream
POOL_SIZE=50          scripts/run-one.sh mvc-platform db-heavy 1000
```

Defaults are `DURATION=60s`, `WARMUP=30s`. Short durations are fine while
exploring; use at least 60s for anything you intend to quote.

## Reading the output

```
  offered rate      1000 rps      <- what k6 tried to send
  completed         29520 (977.1 rps)
  dropped           484           <- see below
  error rate        12.85%
  p50 / p95 / p99   210.3 / 464.3 / 1263.7 ms
  max               1490.9 ms
```

A threshold breach printed by k6 is **a result, not a failure** -- finding the
rate at which the SLA breaks is the point of the ladder.

`dropped` counts iterations k6 could not start. Drops during warmup are
harmless. Drops during the **measured** phase mean the generator failed to offer
the target rate, so the cell is not a valid open-model measurement; the script
writes a `.INVALID` marker file next to it and prints a warning. Never plot a
cell that has one.

Every cell writes into `results/raw/`:

| File | Contents |
| --- | --- |
| `*.k6.json` | full k6 summary, the primary result |
| `*.metrics.before.txt` / `*.after.txt` | Prometheus scrape bracketing the run; difference the counters |
| `*.jfr` | flight recording -- GC, allocation, `jdk.VirtualThreadPinned` |
| `*.app.log` | the variant's stdout |
| `*.INVALID` | present only if the cell must be discarded |

`results/raw/` is gitignored.

## Running a ladder or the full matrix

```bash
scripts/run-matrix.sh                                   # everything
WORKLOADS="api" REPS=3 scripts/run-matrix.sh            # one workload
VARIANTS_OVERRIDE="mvc-platform mvc-virtual" \
  WORKLOADS="api db-heavy" REPS=3 scripts/run-matrix.sh
```

Cell order is randomised so that drift over a long run -- thermal, background
load, a noisy neighbour -- cannot correlate with one variant. The rate ladders
per workload live in `scripts/lib.sh` and are derived in `docs/WORKLOADS.md`.

The full matrix is 4 variants x 5 workloads x ~5 rates x 3 repetitions, roughly
350 cells at 90s each: about **9 hours**. Start with one workload.

## A warning about local numbers

On a laptop the load generator, the application, the stub and Postgres all share
the same CPU, so they compete. Local results are useful for checking that the
harness works and for seeing the *shape* of a difference. They are not quotable,
and they are not stable -- the same cell can differ substantially between runs
depending on what else the machine is doing. Quotable numbers need the
three-instance EC2 setup, where the system under test has CPUs to itself.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `java not found` | `JAVA_HOME` stale; see setup |
| `k6 not found` | reopen terminal, or `export K6_BIN=...` |
| `stub-service not reachable` | run `scripts/env-up.sh` first |
| `missing ...jar` | run `./gradlew bootJar` |
| port 8080 in use | a previous JVM survived; `scripts/env-down.sh` |
| every request 404s | database not seeded; `scripts/env-down.sh --purge` then `env-up.sh` |
