# Running the benchmark

Plain commands, run by hand. Use **Git Bash** on Windows, not PowerShell.

You will want **three terminals**: one for Postgres and ad-hoc commands, one for
the stub service, one for the variant under test. The stub and the variant run
in the foreground so you can see their logs and stop them with Ctrl+C.

Check the toolchain once:

```bash
java -version     # expect 25.0.4
k6 version        # expect v2.2.0
```

---

## Step 1 — Build

```bash
./gradlew bootJar
```

Produces a runnable jar per module under `<module>/build/libs/`. Re-run after
any code change.

## Step 2 — Start Postgres

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

The first start seeds 100k customers, 200k accounts and 2.6M transactions, which
takes about 2.5 minutes. Watch for it to finish:

```bash
docker exec infra-postgres-1 psql -U bench -d bench -tAc "select count(*) from transactions"
```

Wait until this prints `2600000`. Anything less means seeding is still running.
Later starts reuse the volume and are immediate.

## Step 3 — Start the stub service

**Second terminal.** This is the fake downstream that `/api` calls.

```bash
java -jar stub-service/build/libs/stub-service-0.0.1-SNAPSHOT.jar
```

Leave it running. Check it from anywhere:

```bash
curl "http://localhost:9099/upstream?delayMs=200"
```

Only `/api` needs it; the database workloads do not.

## Step 4 — Start the variant you want to measure

**Third terminal.** One at a time — every variant binds port 8080 deliberately,
so the load scripts never change between runs.

```bash
java -Xms1g -Xmx1g -XX:+UseG1GC -jar mvc-platform/build/libs/mvc-platform-0.0.1-SNAPSHOT.jar
```

Swap the module name for any of:

```
mvc-platform    mvc-virtual    webflux-r2dbc    mvc-jpa
```

The JVM flags matter: heap and collector must be **identical across variants**,
or you are comparing GC configurations rather than thread models. Add
`-XX:StartFlightRecording=settings=profile,dumponexit=true,filename=run.jfr` if
you want a flight recording of that run.

Wait for startup, then confirm:

```bash
curl http://localhost:8080/actuator/health
```

Optional overrides, set before `java`:

```bash
POOL_SIZE=50 java -jar ...             # connection pool size, default 20
UPSTREAM_DELAY_MS=500 java -jar ...    # how slow the stub pretends to be
```

## Step 5 — Run the load

Back in the first terminal:

```bash
mkdir -p results/raw

BASE_URL=http://localhost:8080 \
RATE=1000 \
DURATION=60s \
WARMUP=30s \
OUT=results/raw/mvc-platform_api_1000.json \
  k6 run load/scenarios/api.js
```

| Variable | Meaning |
| --- | --- |
| `RATE` | requests per second to **offer** (not to complete) |
| `DURATION` | measured phase |
| `WARMUP` | discarded phase before it |
| `OUT` | where the full JSON summary is written |
| `TIMEOUT_MS` | per-request timeout, default 1000 |

Scenarios in `load/scenarios/`:

```
nodb.js       no database, no upstream — web layer only
db.js         one cheap query (~1ms connection hold)
db-heavy.js   statement query padded to 15ms hold — pool binds at ~1,387 rps
db-slow.js    100ms hold — pool binds at ~200 rps
api.js        200ms upstream call, no database — threads bind at ~1,000 rps
```

## Step 6 — Read the result

```
  offered rate      1000 rps
  completed         30000 (967.7 rps)
  dropped           3
  error rate        15.36%
  p50 / p95 / p99   948.1 / 1000.4 / 1001.0 ms
  max               1023.2 ms
```

A threshold breach printed by k6 is **a result, not a failure**. Finding the rate
at which the SLA breaks is the point of the exercise.

`dropped` is the number to check. Drops during warmup are harmless. Drops during
the measured phase mean k6 could not offer the target rate, so the run is not a
valid open-model measurement — discard it, and either raise `TIMEOUT_MS` headroom
or use a bigger load generator. To see which phase they fell in:

```bash
python -c "import json; m = json.load(open('results/raw/mvc-platform_api_1000.json'))['metrics']; print(m.get('dropped_iterations{scenario:measure}', {}).get('values'))"
```

## Step 7 — Capture the server-side metrics

Before stopping the variant, while it is still running:

```bash
curl -s http://localhost:8080/actuator/prometheus > results/raw/mvc-platform_api_1000.metrics.txt
```

The ones that matter:

```bash
curl -s http://localhost:8080/actuator/prometheus | grep -E 'hikaricp_connections_(pending|active)|r2dbc_pool_(pending|acquired)|jvm_threads_live'
```

A climbing `*_pending` means requests are queueing for a database connection.

## Step 8 — Next run

Ctrl+C the variant's terminal, start the next variant, repeat from step 4. Leave
Postgres and the stub running between variants.

## Stopping

Ctrl+C the stub and variant terminals, then:

```bash
docker compose -f infra/docker-compose.yml stop      # keep the seeded data
docker compose -f infra/docker-compose.yml down -v   # delete it too
```

If a JVM was left behind and port 8080 is busy:

```bash
taskkill //F //IM java.exe //T
```

---

## A worked comparison

Three runs of the decisive workload, one variant at a time:

```bash
# terminal 2, once
java -jar stub-service/build/libs/stub-service-0.0.1-SNAPSHOT.jar
```

```bash
# terminal 3 — start, measure, Ctrl+C, next
java -Xms1g -Xmx1g -XX:+UseG1GC -jar mvc-platform/build/libs/mvc-platform-0.0.1-SNAPSHOT.jar
java -Xms1g -Xmx1g -XX:+UseG1GC -jar mvc-virtual/build/libs/mvc-virtual-0.0.1-SNAPSHOT.jar
java -Xms1g -Xmx1g -XX:+UseG1GC -jar webflux-r2dbc/build/libs/webflux-r2dbc-0.0.1-SNAPSHOT.jar
```

```bash
# terminal 1 — run after each one starts, changing OUT to match
BASE_URL=http://localhost:8080 RATE=1500 DURATION=60s WARMUP=30s \
  OUT=results/raw/mvc-platform_api_1500.json k6 run load/scenarios/api.js
```

## Rate ladders

Derived in `docs/WORKLOADS.md` from the measured knees. Each rate is a separate
k6 invocation.

| Workload | Rates |
| --- | --- |
| `nodb` | 1000 2000 4000 8000 |
| `db` | 400 800 1000 1200 1600 2400 |
| `db-heavy` | 400 800 1000 1200 1600 2400 |
| `db-slow` | 50 100 150 200 300 400 |
| `api` | 250 500 1000 1500 2000 |

Three repetitions each, and vary the order between variants so that drift over a
long session does not land on one variant. The full matrix by hand is several
hundred runs — worth scripting once the EC2 setup exists and this manual flow has
proven itself.

## Local results are not quotable

On one machine the load generator, the application, the stub and Postgres all
compete for the same CPU. The same command can give noticeably different numbers
depending on what else the machine is doing. Local runs are for checking the
harness and seeing the *shape* of a difference. Quotable numbers need the
three-instance EC2 split.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `k6: command not found` | shell predates the install; open a new terminal or use the full path |
| `missing ...jar` | run `./gradlew bootJar` |
| port 8080 already in use | a previous JVM survived; `taskkill //F //IM java.exe //T` |
| every request 404s | database not seeded; check the `count(*)` in step 2 |
| `/api` fails, others fine | stub service not running; see step 3 |

---

# Running on EC2 with the scripts

The manual steps above still work and are the right way to debug a single cell.
For the full matrix, two scripts drive it from your laptop.

## Configure once

Edit the CONFIG block at the top of `scripts/run-benchmark.sh`, or pass the
values as environment variables:

```bash
export KEY=~/.ssh/bench.pem
export SUT_HOST=ubuntu@<sut-public-ip>
export LOADGEN_HOST=ubuntu@<loadgen-public-ip>
export BACKEND_HOST=ubuntu@<backend-public-ip>
export SUT_PRIVATE_IP=10.0.0.11
export BACKEND_PRIVATE_IP=10.0.0.12
```

`BACKEND_HOST` is needed so the script can start the stub if it is not running.

Public addresses for ssh, private addresses for the instances talking to each
other.

## Run from the load generator

One standalone script per workload. No ssh, no orchestration: they talk to the
SUT over HTTP and run k6 locally. You start and stop the variants yourself.

**Once**, copy the scenarios and the runners up:

```bash
scp -i key.pem -r load/scenarios load/lib ubuntu@<loadgen-public>:~/
```

**On the app server**, start one variant:

```bash
cd ~
DB_URL=jdbc:postgresql://<backend-private>:5432/bench DB_USER=bench DB_PASSWORD=bench UPSTREAM_URL=http://<backend-private>:9099 POOL_SIZE=20 nohup java -Xms1g -Xmx1g -XX:+UseG1GC -jar mvc-platform-0.0.1-SNAPSHOT.jar > app.log 2>&1 &
```

`webflux-r2dbc` needs `r2dbc:postgresql://...` instead of `jdbc:`.

**On the load generator**, run the workload:

```bash
cd ~/scenarios
./run-api.sh              # the whole ladder: 250 500 1000 1500 2000
./run-api.sh 1500         # one rate
REPS=1 ./run-api.sh 1500  # one rate, one repetition
```

| script | rates | what it exercises |
| --- | --- | --- |
| `run-nodb.sh` | 1000 2000 4000 8000 | web layer only |
| `run-db.sh` | 400 800 1000 1200 1600 2400 | cheap query, ~1ms hold |
| `run-db-heavy.sh` | 400 800 1000 1200 1600 2400 | 15ms hold, pool binds ~1,387 |
| `run-db-slow.sh` | 50 100 150 200 300 400 | 100ms hold, pool binds ~200 |
| `run-api.sh` | 250 500 1000 1500 2000 | 200ms upstream, threads bind ~1,000 |

Set `SUT=` if the app server's private IP differs from the default in the
script. `OUTDIR=`, `REPS=`, `DURATION=` and `WARMUP=` all override too.

**Results are named after the variant the SUT reports**, not after what you
think you started. Each script reads the `variant` tag from
`/actuator/prometheus`, so starting the wrong jar cannot silently mislabel a
result — and if nothing is running it says so and stops.

Then stop that variant, start the next, and run the same script again.

Fetch everything when you are done:

```bash
scp -i key.pem 'ubuntu@<loadgen-public>:results/*' results/raw/
python scripts/summarize.py
```

Use `tmux` on the load generator for a full ladder, so a dropped SSH session
does not take the run with it.

## Run from your laptop

```bash
scripts/run-benchmark.sh api 500        # one workload, one rate
scripts/run-benchmark.sh api            # one workload, its whole ladder
scripts/run-benchmark.sh all            # everything, several hours
```

Useful overrides:

```bash
REPS=1 DURATION=30s WARMUP=30s scripts/run-benchmark.sh api 1500   # quick check
VARIANTS="mvc-platform mvc-virtual" scripts/run-benchmark.sh api   # two variants
JVM_FLAGS="-Xms128m -Xmx1g -XX:+UseG1GC" scripts/run-benchmark.sh api 500
```

That last one is for **resource measurement only**. A committed heap (`-Xms1g`)
pins RSS near 1GB for every variant and hides the differences. Use the default
fixed heap for latency work, and never mix the two in one comparison.

## What it does per cell

1. Starts the variant on the SUT with the right `DB_URL` scheme (R2DBC for
   `webflux-r2dbc`, JDBC for the rest)
2. Waits for `/actuator/health`
3. Snapshots `/actuator/prometheus`
4. Runs k6 on the load generator
5. Snapshots `/actuator/prometheus` again, **before** stopping the JVM
6. Stops the variant and copies the k6 JSON back

Cell order is shuffled, so drift over a long run cannot correlate with one
variant and masquerade as a result.

A cell where k6 dropped iterations during the measured phase gets a `.INVALID`
marker. Those did not sustain the offered rate and must not be plotted.

## Read the results

```bash
python scripts/summarize.py             # all workloads
python scripts/summarize.py api         # one
python scripts/summarize.py > report.md
```

Prints medians across repetitions with the per-run p99 spread beside them, plus
server-side heap, threads, pool pending and connection hold time. Invalid cells
are listed separately rather than silently dropped.

## Preflight

```bash
scripts/run-benchmark.sh check     # run the checks, then stop
```

Every link in the chain is checked on its own line: ssh to each box, the Java
version, each variant jar, port 8080 free, Postgres reachable **from the SUT**
and seeded to the expected row count, the stub answering, k6 present, all five
scenarios plus `lib/common.js`, and the load generator's path to the SUT.

Postgres is checked from the SUT rather than from your laptop, because that is
the path the application uses and it is governed by a different security group
rule.

The stub is verified by measuring it, not by trusting `/actuator/health`: the
script calls `?delayMs=200` and confirms the response takes about 200ms. A stub
that answers health while ignoring the delay would turn every `/api` cell into a
measurement of something other than a 200ms upstream call.

## The stub is started automatically

If the stub is not running, the script starts it on `BACKEND_HOST` and waits for
it, rather than failing. This happens in preflight and again before every `/api`
cell, so a stub that crashes mid-matrix costs a few seconds instead of silently
turning every remaining `/api` cell into a measurement of connection refusals.

It gives up only if `BACKEND_HOST` is unreachable or `$STUB_JAR` is missing from
`$BACKEND_DIR`, and prints the stub's own log when a start attempt fails.

Postgres is *not* started automatically — it is a container with a seeded volume,
and restarting it blindly could hide a real problem. A failed Postgres check
names what is wrong and stops.
