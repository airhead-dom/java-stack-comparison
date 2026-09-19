# Resource usage — CPU and memory

**Not quotable** (shared laptop), but measured properly rather than sampled once.
Workload is `/api` — one 200ms upstream call, no database — so nothing here is
attributable to the connection pool.

## Method

- `-Xms128m -Xmx1g -XX:+UseG1GC`. **Not** the usual `-Xms1g`: committing the full
  heap up front pins RSS near 1GB for every variant and hides the difference
  entirely. An earlier attempt with `-Xms1g` returned RSS 849–1008MB across all
  four, which measured the flag and not the application.
- **CPU** from `process_cpu_time_ns_total` differenced across the measured window
  and divided by wall time. `cores = 1.000` means one core fully saturated. This
  is cumulative CPU actually consumed, not a sampled instantaneous gauge.
- **RSS** from `Get-Process.WorkingSet64`, **heap** and **nonheap** from
  Micrometer, **13 samples 2s apart** during the measured phase, median reported.
- 20s warmup discarded, 30s measured, 500 and 1,000 rps.

## `/api` @ 500 rps — ~105 in flight, all four healthy

Same work, same latency, zero errors everywhere. Differences are cost, not
capability.

| variant | cores | RSS MB | heap MB | nonheap MB | threads | p99 ms | errors % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| webflux-r2dbc | **0.222** | **303** | **63** | 86 | **31** | 217.4 | 0.00 |
| mvc-virtual | 0.315 | 349 | 129 | 79 | 197 | 218.6 | 0.00 |
| mvc-platform | 0.350 | 352 | 125 | 78 | 309 | 327.3 | 0.00 |
| mvc-jpa | 0.352 | 417 | 134 | 121 | 307 | 217.3 | 0.00 |

Relative to `webflux-r2dbc`:

| variant | CPU | RSS | heap | threads |
| --- | ---: | ---: | ---: | ---: |
| mvc-virtual | ×1.42 | ×1.15 | ×2.04 | ×6.4 |
| mvc-platform | ×1.58 | ×1.16 | ×1.98 | ×10.0 |
| mvc-jpa | ×1.59 | ×1.38 | ×2.13 | ×9.9 |

**CPU is the real difference, not memory.** Reactive uses ~30% less CPU than
either blocking variant for identical work. RSS differs by only 15% despite a 6–10x
thread count, because thread stacks are reserved lazily — a mostly-idle thread
waiting on a socket never touches most of its stack, so it costs address space
rather than resident pages.

**Virtual threads sit between the two on CPU** (×1.42 vs ×1.58), and use a third
fewer OS threads than platform while doing the same work.

**mvc-jpa is the most expensive on memory** — 417MB RSS and 121MB nonheap, the
latter being Hibernate's metadata in Metaspace.

## `/api` @ 1,000 rps — ~200 in flight, at Tomcat's ceiling

| variant | completed rps | cores | RSS MB | heap MB | threads | p99 ms | errors % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| webflux-r2dbc | 996 | **0.380** | **310** | **52** | **31** | 217.8 | 0.00 |
| mvc-virtual | 996 | 0.517 | 514 | 178 | 568 | 217.9 | 0.00 |
| mvc-platform | 980 | 0.458 | 462 | 160 | 382 | 1199.7 | **100.00** |

`mvc-platform`'s numbers are **not comparable** — it failed every request, so it
is consuming CPU and memory while producing nothing. Listed only to show it was
not resource-starved when it collapsed: it had CPU headroom and was under its
heap ceiling. The failure is the thread limit, not a lack of resources.

## How cost scales with load

Doubling offered rate from 500 to 1,000 rps:

| variant | cores | RSS MB | heap MB |
| --- | --- | --- | --- |
| webflux-r2dbc | 0.222 → 0.380 (+71%) | 303 → 310 (**+2%**) | 63 → 52 (−17%) |
| mvc-virtual | 0.315 → 0.517 (+64%) | 349 → **514** (+47%) | 129 → 178 (+38%) |
| mvc-platform | 0.350 → 0.458 (+31%) | 352 → 462 (+31%) | 125 → 160 (+28%) |

**This is the finding that matters.** Reactive's memory is flat in concurrency —
RSS moved 2% for twice the load, because an in-flight request is a small
continuation object, not a stack. Virtual threads cost +47% RSS for the same
doubling, because each in-flight request carries a real stack on the heap.

Extrapolating is unsafe from two points, but the *shapes* differ: one is roughly
flat, the other roughly linear in concurrency. At your 1,000 TPS target with
200ms upstream calls, `mvc-virtual` needed ~514MB against reactive's ~310MB.

## Correction to an earlier claim

I previously reported virtual threads using **465MB of heap against webflux's
19MB — "roughly 24x"** on `/api` at 1,500 rps. That figure should not be used:

- It was a **single sample** taken once after the run, and heap sawtooths with
  GC, so the reading depends on where in a GC cycle it landed.
- It ran with `-Xms1g`, so the heap was committed regardless of demand.
- It came from a rate where `mvc-platform` was failing, so the variants were not
  doing comparable work.

Measured properly, the heap ratio is **~2x at 500 rps and ~3.4x at 1,000 rps**,
and RSS — which is what an instance actually needs — differs by 15% and 66%
respectively. The mechanism I described was right; the magnitude was wrong by an
order of magnitude.

## What this does not cover

- **One run per cell.** No repetitions, so treat single-digit-percent differences
  as noise. The CPU ordering held across both rates, which is mild corroboration.
- **CPU figures include the JVM's own overhead** (GC threads, JIT compilation)
  and are contaminated by k6, Postgres and the stub sharing the machine.
- **Database workloads not measured** for resources — `/api` was chosen so the
  connection pool could not be a confound.
- **RSS on Windows** is not the same as RSS under a Linux cgroup, which is what
  will actually constrain a container. Re-measure on EC2 before sizing anything.
