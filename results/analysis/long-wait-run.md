# The long-wait run — `/api-800` and `/api-1000`

Two workloads that hold each request at the upstream for 800 ms and
1,000 ms, against the two migration candidates. No database is involved,
so nothing the connection pool does can explain anything here.

The question is what each stack spends to hold a request that is merely
**waiting**. The earlier `/api` workload was sized so that in-flight
concurrency landed on Tomcat's 200 threads, which made it decisive about
`mvc-platform`. These two are sized past any thread count either
candidate has, so the scarce resource is no longer a worker to run the
request on — it is whatever the stack must keep alive while nothing is
happening.

This report is deliberately **descriptive**. It states what was measured
and, where the data supports one, the mechanism behind it. It does not
draw a conclusion about whether to migrate.

## How to read this

**Latency is reported as excess over the delay floor.** Every request
must wait out the upstream delay, so a raw p99 of 1,087 ms mostly
measures the stub. The floor is subtracted throughout: `+87` means 87 ms
of latency that the application added on top of the wait. Raw figures
are in the appendix.

**In-flight count is measured, not inferred.** This is the first run
carrying a mid-run sampler: `/actuator/prometheus` was scraped every 2 s
for the whole of each cell, giving ~54 steady-state readings of
in-flight, heap, CPU, threads and file descriptors. Previous runs had one
reading either side of the window, both taken while the system was idle,
which for a gauge means in-flight reads 0 and heap reads wherever GC
happened to leave it.

**Both repetitions are always shown.** Nothing is averaged across reps
in the per-cell tables, so where the two disagree it is visible rather
than smoothed away.

**Heap is reported as a floor, not a mean.** Heap used sawtooths with
GC, so its mean mixes retained state with uncollected garbage. The
minimum reading while under load is the part that did not go away.

## Coverage

32 cells: 2 builds x 2 workloads x 4 rates x 2 repetitions.

- **32 of 32 valid.** Every cell sustained its offered rate:
  0 dropped iterations and 0.00 % errors throughout, with no `.INVALID`
  or `.SKIPPED` marker on disk.
- `mvc-platform` and `mvc-jpa` do not implement these endpoints and were
  not run. 200 Tomcat threads over an 800 ms hold caps `mvc-platform` at
  250 rps, below the bottom rung of the ladder.
- 60 s warmup discarded, 60 s measured, open model, two repetitions.
- SUT: c7i.large, 2 vCPU, `-Xms1g -Xmx1g -XX:+UseG1GC`. Load generator:
  m7i.large, 2 vCPU, 8 GiB.

## In-flight capacity

Neither build reached a ceiling. Measured in-flight tracks Little's Law
(`rate x latency`) at every rung, on both builds, to within 1 %.

| workload | offered | expected | webflux-r2dbc | mvc-virtual |
| --- | ---: | ---: | ---: | ---: |
| `api-800` | 500 | 400 | 400 / 400 | 400 / 400 |
| `api-800` | 1,000 | 800 | 800 / 801 | 802 / 800 |
| `api-800` | 1,500 | 1,200 | 1,202 / 1,201 | 1,204 / 1,205 |
| `api-800` | 2,000 | 1,600 | 1,602 / 1,601 | 1,617 / 1,604 |
| `api-1000` | 500 | 500 | 500 / 500 | 502 / 501 |
| `api-1000` | 1,000 | 1,000 | 1,001 / 1,001 | 1,002 / 1,001 |
| `api-1000` | 1,500 | 1,500 | 1,501 / 1,501 | 1,503 / 1,502 |
| `api-1000` | 2,000 | 2,000 | 2,001 / 2,003 | 2,009 / 2,011 |

Peak readings run higher than the mean — the sampler catches the
momentary backlog when a GC pause or a scheduling hiccup briefly holds
requests up. At `/api-1000` @ 2,000 rps the peaks were
**2,196** for `mvc-virtual` against **2,046** for
`webflux-r2dbc`, against a steady state of ~2,000 for both. The backlog
is a consequence of the pauses reported further down, not a separate
finding.

## Response time

**p50 is the delay itself** on both builds at every rate — 800.5-800.9 ms
and 1000.5-1000.9 ms. Half of all requests pay nothing above the wait,
whichever stack serves them. The entire difference between the builds
lives in the tail.

p99 excess over the delay floor, in ms, both repetitions:

| workload | rate | webflux-r2dbc | mvc-virtual | ratio |
| --- | ---: | ---: | ---: | ---: |
| `api-800` | 500 | +2 / +2 | +26 / +3 | 7.6x |
| `api-800` | 1,000 | +9 / +9 | +64 / +63 | 7.2x |
| `api-800` | 1,500 | +15 / +14 | +80 / +77 | 5.5x |
| `api-800` | 2,000 | +22 / +22 | +86 / +86 | 3.8x |
| `api-1000` | 500 | +2 / +2 | +23 / +2 | 8.0x |
| `api-1000` | 1,000 | +10 / +11 | +65 / +67 | 6.4x |
| `api-1000` | 1,500 | +20 / +20 | +80 / +80 | 4.1x |
| `api-1000` | 2,000 | +31 / +29 | +87 / +83 | 2.9x |

The two repetitions agree closely at every rung above 500 rps — 86 and
86, 80 and 77, 87 and 84 — so the separation is reproducible rather than
a single bad run. At 500 rps both builds are close enough to the floor
that rep-to-rep noise dominates: `mvc-virtual` posted +26 and +3 ms on
the same cell.

## What drives the tail, and what drives the heap

Offered rate and in-flight count normally move together — in flight is
`rate x delay` — so within one workload neither can be blamed. Running
two delays breaks the tie: **at the same offered rate, the two workloads
sit at different in-flight counts.** If a cost followed concurrency,
those pairs would diverge.

p99 excess at matched rates, averaged over both reps:

| rate | build | `/api-800` | `/api-1000` | change |
| ---: | --- | ---: | ---: | ---: |
| 500 | webflux-r2dbc | +2 ms at 400 | +2 ms at 500 | -0.3 ms |
| 500 | mvc-virtual | +14 ms at 400 | +12 ms at 501 | -2.0 ms |
| 1,000 | webflux-r2dbc | +9 ms at 801 | +10 ms at 1,001 | +1.5 ms |
| 1,000 | mvc-virtual | +64 ms at 801 | +66 ms at 1,002 | +2.5 ms |
| 1,500 | webflux-r2dbc | +14 ms at 1,201 | +20 ms at 1,501 | +5.4 ms |
| 1,500 | mvc-virtual | +79 ms at 1,204 | +80 ms at 1,503 | +1.3 ms |
| 2,000 | webflux-r2dbc | +22 ms at 1,602 | +30 ms at 2,002 | +7.6 ms |
| 2,000 | mvc-virtual | +86 ms at 1,610 | +85 ms at 2,010 | -0.4 ms |

**For `mvc-virtual` the tail does not follow in-flight at all.** Adding
25 % more concurrency at a fixed rate moves p99 by -2.0, +2.5, +1.3 and
-0.4 ms — inside the noise, and the sign flips. Its ~86 ms tail is a
**per-request** cost that scales with throughput, not with how many
requests are parked.

**For `webflux-r2dbc` the picture is not as clean, and it should not be
reported as though it were.** The same pairs give -0.3, +1.5, +5.4 and
+7.6 ms. The last two are not noise: at 2,000 rps, going from 1,602 to
2,002 in flight adds 7.6 ms to a 22 ms baseline, about a third. Its tail
is much smaller in absolute terms but does pick up a concurrency
component above roughly 1,500 requests in flight.

Heap goes the other way. Regressing the heap floor on measured in-flight
across all 16 cells of each build:

| build | per request in flight | intercept | R² |
| --- | ---: | ---: | ---: |
| webflux-r2dbc | **26 KB** | 34 MB | 0.59 |
| mvc-virtual | **166 KB** | 212 MB | 0.66 |

The R² values are moderate, so these are trends rather than tight fits —
the heap floor is noisy at the bottom of the ladder, where few
collections run during a 120 s window and the minimum reading is
whatever the last one happened to leave. The direction and the order of
magnitude are solid; the exact slope is not.

The `mvc-virtual` figure is consistent with the 139 KB per queued
request measured on `/db-heavy` at overload in the AWS run, which arrived
by a completely different route — pool exhaustion rather than deliberate
upstream delay.

## CPU

Of 2 available cores, averaged over the steady-state samples:

| workload | rate | webflux-r2dbc | mvc-virtual | ratio |
| --- | ---: | ---: | ---: | ---: |
| `api-800` | 500 | 0.112 / 0.082 | 0.147 / 0.104 | 1.3x |
| `api-800` | 1,000 | 0.115 / 0.121 | 0.158 / 0.158 | 1.3x |
| `api-800` | 1,500 | 0.142 / 0.142 | 0.226 / 0.228 | 1.6x |
| `api-800` | 2,000 | 0.142 / 0.165 | 0.299 / 0.308 | 2.0x |
| `api-1000` | 500 | 0.080 / 0.079 | 0.103 / 0.097 | 1.3x |
| `api-1000` | 1,000 | 0.119 / 0.118 | 0.164 / 0.163 | 1.4x |
| `api-1000` | 1,500 | 0.145 / 0.144 | 0.229 / 0.233 | 1.6x |
| `api-1000` | 2,000 | 0.164 / 0.168 | 0.332 / 0.340 | 2.0x |

The ratio is close to **2x** across the top of the ladder and holds on
both workloads. Neither build is near saturating the box: at the most
expensive cell `mvc-virtual` used 0.34 of 2 cores, so the CPU difference
is a cost difference, not a throughput limit at these rates.

## Memory

Three separate measurements, which say different things.

**Allocation** is a counter, so differencing two scrapes is exact.
Normalised per 1,000 requests it is near-constant across the ladder,
which makes it comparable between builds:

| workload | rate | webflux-r2dbc MB/1k | mvc-virtual MB/1k | ratio |
| --- | ---: | ---: | ---: | ---: |
| `api-800` | 500 | 39 / 39 | 75 / 76 | 1.9x |
| `api-800` | 1,000 | 39 / 35 | 66 / 70 | 1.8x |
| `api-800` | 1,500 | 39 / 36 | 65 / 67 | 1.8x |
| `api-800` | 2,000 | 39 / 39 | 63 / 64 | 1.6x |
| `api-1000` | 500 | 40 / 30 | 77 / 77 | 2.2x |
| `api-1000` | 1,000 | 40 / 40 | 69 / 68 | 1.7x |
| `api-1000` | 1,500 | 39 / 36 | 66 / 66 | 1.8x |
| `api-1000` | 2,000 | 38 / 39 | 65 / 66 | 1.7x |

`mvc-virtual` allocates roughly **1.7x** as much per request. That is the
same direction and close to the same magnitude as the AWS `/api` cells
(59 against 37 MB per 1,000 at 2,000 rps), now reproduced at four to
five times the in-flight count.

**Promotion** is where the two builds stop resembling each other. This
counts bytes that survived a young collection and were moved to the old
generation:

| workload | rate | webflux-r2dbc KB/req | mvc-virtual KB/req |
| --- | ---: | ---: | ---: |
| `api-800` | 500 | 0.0 / 0.0 | 5.4 / 1.1 |
| `api-800` | 1,000 | 0.2 / 0.0 | 8.1 / 5.2 |
| `api-800` | 1,500 | 0.0 / 0.0 | 4.9 / 4.9 |
| `api-800` | 2,000 | 0.0 / 0.0 | 4.5 / 5.4 |
| `api-1000` | 500 | 0.0 / 0.0 | 4.9 / 1.3 |
| `api-1000` | 1,000 | 0.0 / 0.0 | 5.5 / 5.9 |
| `api-1000` | 1,500 | 0.0 / 0.0 | 5.0 / 6.2 |
| `api-1000` | 2,000 | 0.0 / 0.0 | 7.2 / 6.5 |

`webflux-r2dbc` promotes **essentially nothing**: its largest cell is
0.20 KB per request and the other 15 are under 0.03 KB. `mvc-virtual`
promotes around **5 KB per request** — between 25x and 400x more,
depending which WebFlux cell it is set against.

That is the mechanism behind the heap slope. A request that waits a
second is alive far longer than a young collection cycle at these
allocation rates, so under virtual threads its stack is still reachable
when the collector runs and gets promoted. The reactive build holds the
same waiting request as a small callback chain that either dies young or
was never big enough to matter. Both are paying to remember a request
that is doing nothing; they differ in how much there is to remember and
in which generation it ends up.

**GC pause**, summed over the 120 s window:

| workload | rate | webflux-r2dbc pause / count | mvc-virtual pause / count |
| --- | ---: | ---: | ---: |
| `api-800` | 500 | 0.00 s (0) / 0.15 s (4) | 0.00 s (0) / 0.14 s (9) |
| `api-800` | 1,000 | 0.31 s (8) / 0.12 s (7) | 1.60 s (20) / 1.48 s (17) |
| `api-800` | 1,500 | 0.30 s (12) / 0.27 s (11) | 2.39 s (27) / 2.38 s (28) |
| `api-800` | 2,000 | 0.53 s (16) / 0.52 s (16) | 3.51 s (41) / 3.62 s (43) |
| `api-1000` | 500 | 0.05 s (4) / 0.04 s (3) | 0.77 s (10) / 0.19 s (8) |
| `api-1000` | 1,000 | 0.17 s (8) / 0.17 s (8) | 1.52 s (17) / 1.62 s (18) |
| `api-1000` | 1,500 | 0.37 s (12) / 0.33 s (11) | 2.60 s (30) / 2.70 s (31) |
| `api-1000` | 2,000 | 0.64 s (16) / 0.63 s (16) | 4.46 s (51) / 4.62 s (55) |

At the top rung `mvc-virtual` spends about **7x** as long paused, over
roughly three times as many collections. Against a 120 s window, 4.5 s of
pause is ~3.7 % of wall clock, which is consistent with the tail excess
being what it is without accounting for all of it.

## Threads and file descriptors

`jvm_threads_live_threads` counts Java platform threads only — virtual
threads are excluded, and so are the JVM's native GC and JIT threads. For
`mvc-virtual` this is therefore a count of ForkJoinPool carriers plus
Tomcat's own threads, not of requests.

| workload | rate | webflux-r2dbc threads | mvc-virtual threads | webflux-r2dbc peak fds | mvc-virtual peak fds |
| --- | ---: | ---: | ---: | ---: | ---: |
| `api-800` | 500 | 22 | 51 | 1,533 | 1,545 |
| `api-800` | 1,000 | 21 | 59 | 3,011 | 3,049 |
| `api-800` | 1,500 | 21 | 109 | 4,490 | 4,559 |
| `api-800` | 2,000 | 21 | 125 | 5,958 | 6,080 |
| `api-1000` | 500 | 21 | 42 | 3,060 | 1,910 |
| `api-1000` | 1,000 | 21 | 68 | 4,372 | 3,777 |
| `api-1000` | 1,500 | 21 | 71 | 5,686 | 5,645 |
| `api-1000` | 2,000 | 21 | 115 | 7,413 | 8,083 |

`webflux-r2dbc` sits at **21 threads in fifteen of sixteen cells**, and
22.7 in the sixteenth — it does not matter what the rate is or how many
requests are in flight, which is the event loop model doing exactly what
it claims. `mvc-virtual` grows from
40 to around 130 carriers. Carrier growth of that size on a 2-core box
means the scheduler is compensating for virtual threads that blocked in a
way it could not simply unmount; this data does not establish where.

File descriptors are near-identical between the builds and scale with
concurrency as expected — each in-flight request pins an inbound socket
and an outbound one, on top of the generator's keep-alive pool. Both
builds passed 6,000 at the top rung, well beyond the 1,024 that some
distributions still default to, though the SUT's limit was 1,048,576 so
nothing bound.

## Findings

1. **Both builds held 2,000 requests in flight** with zero errors and
   zero dropped iterations. Neither reached a ceiling on this ladder, so
   no saturation point was measured for either.
2. **Median latency is identical** — the delay floor, on both builds, at
   every rate. Any difference between these stacks on this workload is a
   tail phenomenon.
3. **`mvc-virtual`'s tail is ~3-4x larger** than `webflux-r2dbc`'s
   (+86 vs +22 ms at the top rung) and is a per-request cost: it tracks
   offered rate and is flat against in-flight count.
4. **`webflux-r2dbc`'s tail is smaller but not purely per-request.** It
   picks up a concurrency component above ~1,500 in flight, worth about
   a third of its total at 2,000 rps.
5. **CPU differs by ~2x** at the top of the ladder, on both workloads,
   reproducibly.
6. **The two builds have opposite memory profiles.** `mvc-virtual`
   allocates ~1.7x more per request, promotes ~5 KB per request against
   approximately zero, and its heap floor rises with in-flight count;
   `webflux-r2dbc`'s floor is close to flat.
7. **Thread count is flat for the reactive build** — 21 in fifteen of
   sixteen cells, independent of rate and concurrency — and grows to
   ~130 carriers for virtual threads.

## Limits of this run

**The stub was not independently witnessed.** The runners sample the
stub's own metrics as evidence it never became the bottleneck. All 32
of its CSVs sampled on cadence but recorded zeros throughout, so that
evidence is unavailable for this run. The most likely cause is that the
previous stub build was still running: `stub.sh start` returns early when
one is already alive, so uploading a new jar without `restart` keeps the
old process, and the old build exposed only `health`, not `prometheus`.
A `./stub.sh restart` before the next run would close it. This report
does not argue the point either way — the stub's behaviour during these
cells is simply not established by measurement.

**No ceiling was found**, so nothing here says where either build stops.
These are points on a curve. Extrapolating the heap slope past 2,000 in
flight would be unsupported.

**One configuration.** c7i.large, 2 vCPU, 1 GB heap, G1, one pool size,
one upstream. The 1 GB heap in particular interacts with the promotion
finding: a larger heap would change collection frequency and therefore
both the pause totals and the heap floor.

**Carrier growth is unexplained.** `mvc-virtual` reaching ~130 carrier
threads is visible in the data but its cause is not. A thread dump under
load (`jcmd <pid> Thread.print`) would settle it; nothing here does.

**`mvc-platform` is absent by construction**, so this run says nothing
about platform threads on long waits beyond the arithmetic that excluded
them: 200 threads over an 800 ms hold is 250 rps.

## Appendix — every cell

Raw latency, not excess. `in flight` and `heap floor` are steady-state
readings from the mid-run sampler; the rest are k6 or differenced
counters.

### `/api-800` — 800 ms upstream delay

| rate | build | rep | err % | p50 | p95 | p99 | max | in flight | cores | heap floor | MB/1k | promKB | GC s |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | webflux-r2dbc | 1 | 0.00 | 800.9 | 801.3 | 801.9 | 841.0 | 400 | 0.112 | 38 MB | 39 | 0.0 | 0.00 |
| 500 | webflux-r2dbc | 2 | 0.00 | 800.9 | 801.3 | 801.9 | 843.0 | 400 | 0.082 | 38 MB | 39 | 0.0 | 0.15 |
| 500 | mvc-virtual | 1 | 0.00 | 800.9 | 801.4 | 826.2 | 903.1 | 400 | 0.147 | 181 MB | 75 | 5.4 | 0.00 |
| 500 | mvc-virtual | 2 | 0.00 | 800.9 | 801.3 | 802.8 | 817.1 | 400 | 0.104 | 451 MB | 76 | 1.1 | 0.14 |
| 1,000 | webflux-r2dbc | 1 | 0.00 | 800.5 | 801.0 | 808.9 | 845.4 | 800 | 0.115 | 43 MB | 39 | 0.2 | 0.31 |
| 1,000 | webflux-r2dbc | 2 | 0.00 | 800.6 | 801.0 | 808.9 | 821.0 | 801 | 0.121 | 45 MB | 35 | 0.0 | 0.12 |
| 1,000 | mvc-virtual | 1 | 0.00 | 800.5 | 801.3 | 864.3 | 909.2 | 802 | 0.158 | 356 MB | 66 | 8.1 | 1.60 |
| 1,000 | mvc-virtual | 2 | 0.00 | 800.5 | 801.4 | 863.2 | 915.1 | 800 | 0.158 | 380 MB | 70 | 5.2 | 1.48 |
| 1,500 | webflux-r2dbc | 1 | 0.00 | 800.5 | 801.1 | 814.7 | 830.4 | 1,202 | 0.142 | 64 MB | 39 | 0.0 | 0.30 |
| 1,500 | webflux-r2dbc | 2 | 0.00 | 800.5 | 801.0 | 813.8 | 830.6 | 1,201 | 0.142 | 58 MB | 36 | 0.0 | 0.27 |
| 1,500 | mvc-virtual | 1 | 0.00 | 800.5 | 813.6 | 880.3 | 928.2 | 1,204 | 0.226 | 418 MB | 65 | 4.9 | 2.39 |
| 1,500 | mvc-virtual | 2 | 0.00 | 800.5 | 812.7 | 877.0 | 920.4 | 1,205 | 0.228 | 400 MB | 67 | 4.9 | 2.38 |
| 2,000 | webflux-r2dbc | 1 | 0.00 | 800.5 | 801.2 | 822.2 | 860.1 | 1,602 | 0.142 | 61 MB | 39 | 0.0 | 0.53 |
| 2,000 | webflux-r2dbc | 2 | 0.00 | 800.5 | 801.3 | 822.5 | 864.8 | 1,601 | 0.165 | 66 MB | 39 | 0.0 | 0.52 |
| 2,000 | mvc-virtual | 1 | 0.00 | 800.6 | 829.3 | 886.0 | 1,004.6 | 1,617 | 0.299 | 492 MB | 63 | 4.5 | 3.51 |
| 2,000 | mvc-virtual | 2 | 0.00 | 800.6 | 832.4 | 885.8 | 930.4 | 1,604 | 0.308 | 475 MB | 64 | 5.4 | 3.62 |

### `/api-1000` — 1000 ms upstream delay

| rate | build | rep | err % | p50 | p95 | p99 | max | in flight | cores | heap floor | MB/1k | promKB | GC s |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | webflux-r2dbc | 1 | 0.00 | 1,000.9 | 1,001.3 | 1,001.6 | 1,016.2 | 500 | 0.080 | 62 MB | 40 | 0.0 | 0.05 |
| 500 | webflux-r2dbc | 2 | 0.00 | 1,000.9 | 1,001.3 | 1,001.6 | 1,015.3 | 500 | 0.079 | 65 MB | 30 | 0.0 | 0.04 |
| 500 | mvc-virtual | 1 | 0.00 | 1,000.9 | 1,001.3 | 1,022.9 | 1,101.4 | 502 | 0.103 | 300 MB | 77 | 4.9 | 0.77 |
| 500 | mvc-virtual | 2 | 0.00 | 1,000.9 | 1,001.3 | 1,002.1 | 1,021.5 | 501 | 0.097 | 181 MB | 77 | 1.3 | 0.19 |
| 1,000 | webflux-r2dbc | 1 | 0.00 | 1,000.6 | 1,001.0 | 1,010.2 | 1,026.1 | 1,001 | 0.119 | 66 MB | 40 | 0.0 | 0.17 |
| 1,000 | webflux-r2dbc | 2 | 0.00 | 1,000.6 | 1,001.0 | 1,010.6 | 1,025.6 | 1,001 | 0.118 | 59 MB | 40 | 0.0 | 0.17 |
| 1,000 | mvc-virtual | 1 | 0.00 | 1,000.5 | 1,001.7 | 1,065.4 | 1,105.8 | 1,002 | 0.164 | 312 MB | 69 | 5.5 | 1.52 |
| 1,000 | mvc-virtual | 2 | 0.00 | 1,000.5 | 1,002.5 | 1,067.0 | 1,128.2 | 1,001 | 0.163 | 390 MB | 68 | 5.9 | 1.62 |
| 1,500 | webflux-r2dbc | 1 | 0.00 | 1,000.5 | 1,001.1 | 1,019.8 | 1,062.9 | 1,501 | 0.145 | 72 MB | 39 | 0.0 | 0.37 |
| 1,500 | webflux-r2dbc | 2 | 0.00 | 1,000.5 | 1,001.1 | 1,019.6 | 1,054.7 | 1,501 | 0.144 | 98 MB | 36 | 0.0 | 0.33 |
| 1,500 | mvc-virtual | 1 | 0.00 | 1,000.5 | 1,018.5 | 1,080.4 | 1,120.1 | 1,503 | 0.229 | 460 MB | 66 | 5.0 | 2.60 |
| 1,500 | mvc-virtual | 2 | 0.00 | 1,000.5 | 1,018.4 | 1,079.6 | 1,125.0 | 1,502 | 0.233 | 468 MB | 66 | 6.2 | 2.70 |
| 2,000 | webflux-r2dbc | 1 | 0.00 | 1,000.5 | 1,003.2 | 1,030.6 | 1,088.4 | 2,001 | 0.164 | 83 MB | 38 | 0.0 | 0.64 |
| 2,000 | webflux-r2dbc | 2 | 0.00 | 1,000.5 | 1,004.8 | 1,029.2 | 1,060.1 | 2,003 | 0.168 | 96 MB | 39 | 0.0 | 0.63 |
| 2,000 | mvc-virtual | 1 | 0.00 | 1,000.6 | 1,042.9 | 1,087.4 | 1,137.3 | 2,009 | 0.332 | 530 MB | 65 | 7.2 | 4.46 |
| 2,000 | mvc-virtual | 2 | 0.00 | 1,000.6 | 1,040.5 | 1,083.5 | 1,121.9 | 2,011 | 0.340 | 528 MB | 66 | 6.5 | 4.62 |

---

Generated by `scripts/render_long_wait.py` from `results/raw/`.
