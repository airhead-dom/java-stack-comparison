// Shared configuration for every workload script.
//
// All scenarios use the open model (constant-arrival-rate): the generator keeps
// offering the target rate whether or not the system keeps up. A closed model
// would quietly send less load as the system slowed, hiding exactly the
// saturation behaviour this benchmark exists to measure.

export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
export const RATE = Number(__ENV.RATE || 1000);
export const DURATION = __ENV.DURATION || '60s';
export const WARMUP = __ENV.WARMUP || '30s';
export const SLA_MS = Number(__ENV.SLA_MS || 500);
export const ACCOUNT_MAX = Number(__ENV.ACCOUNT_MAX || 200000);
// A request slower than this has already failed the 500ms SLA several times
// over. Bounding it bounds how many requests can be in flight, which is what
// makes the VU pool sizeable at all.
export const TIMEOUT_MS = Number(__ENV.TIMEOUT_MS || 1000);
export const PARAMS = { timeout: `${TIMEOUT_MS}ms` };
// A hard ceiling on VUs, for generators that cannot afford the derived one.
// Unset means no clamp, which is every workload whose in-flight count is small.
export const VU_BUDGET = Number(__ENV.VU_BUDGET || 0);

// Spread reads across the whole table. Hammering one account would measure
// Postgres' cache and the JVM's, not the system.
export function randomAccountId() {
  return 1 + Math.floor(Math.random() * ACCOUNT_MAX);
}

/**
 * @param expectedLatencyMs healthy latency for this workload, kept for
 *        documentation; VU sizing deliberately uses the timeout instead.
 */
export function buildOptions(expectedLatencyMs) {
  return workload({ latencyMs: expectedLatencyMs }).options;
}

/**
 * The same thing with the per-workload knobs exposed. The defaults reproduce
 * buildOptions exactly, so the five original scenarios are unaffected.
 *
 * @param latencyMs healthy latency for this workload, for VU sizing
 * @param timeoutMs request timeout. The 1,000ms default fails every request of
 *        a workload whose healthy latency is near or above it, so the long-wait
 *        scenarios must set their own.
 * @param slaMs the p99 threshold
 * @param vuMargin pre-allocation margin over healthy concurrency
 * @returns { options, params, preAllocatedVUs, maxVUs, clampedFrom }
 */
export function workload({ latencyMs, timeoutMs = 1000, slaMs = 500, vuMargin = 4 }) {
  const timeout = Number(__ENV.TIMEOUT_MS || timeoutMs);
  const sla = Number(__ENV.SLA_MS || slaMs);

  // Two different numbers, for two different jobs.
  //
  // preAllocatedVUs is created up front and costs memory - roughly 2MB each.
  // Size it from HEALTHY concurrency (Little's Law: rate x latency) with a 4x
  // margin. The margin is what prevents iterations being dropped while the
  // pool grows during ramp-up; 50 was far too few and cost a third of the
  // offered load on an early run.
  //
  // That 4x assumes healthy concurrency is a small number. On the long-wait
  // workloads it is not - /api-1000 at 2,000 rps is 2,000 in flight before any
  // margin at all - so those scenarios pass a much smaller one. Multiplying an
  // already-large number by four is what would exhaust the generator.
  const healthyInFlight = RATE * (latencyMs / 1000);
  const preAllocatedVUs = Math.max(100, Math.ceil(healthyInFlight * vuMargin));

  // maxVUs is only a ceiling. k6 grows into it if latency degrades, and unused
  // headroom costs nothing, so size it for the SATURATED case: under overload
  // latency climbs until it hits the timeout, making worst-case concurrency
  // rate x timeout. Measured latency once reached 1,333ms against a healthy
  // 210ms, and a pool sized for healthy alone ran dry mid-run.
  //
  // Sizing pre-allocation from the timeout instead would be ruinous: /nodb at
  // 8,000 rps serves ~8 concurrent requests but would pre-allocate 9,600 VUs,
  // about 19GB, for no benefit.
  const wanted = Math.max(preAllocatedVUs,
                          Math.ceil(RATE * (timeout / 1000) * 1.2));

  // "Headroom costs nothing" stops being true once the headroom exceeds the
  // generator's memory. An overload cell really does grow into maxVUs, and a
  // generator that dies mid-ladder loses every cell after it as well. Clamping
  // instead makes the cell drop iterations, which the runners already detect
  // and mark .INVALID: a cell that fails honestly, rather than one that takes
  // the rest of the run down with it.
  const clamped = VU_BUDGET > 0 && wanted > VU_BUDGET;
  const maxVUs = clamped ? Math.max(preAllocatedVUs, VU_BUDGET) : wanted;

  const options = {
    // k6 reports avg/med/p(90)/p(95) by default; the SLA is stated at p99 and
    // tail behaviour is the point of the exercise.
    summaryTrendStats: ['min', 'avg', 'p(50)', 'p(95)', 'p(99)', 'p(99.9)', 'max'],
    // The generator must never be the bottleneck; parsing bodies it does not
    // need is wasted CPU on the load box.
    discardResponseBodies: true,
    scenarios: {
      warmup: {
        executor: 'constant-arrival-rate',
        rate: RATE,
        timeUnit: '1s',
        duration: WARMUP,
        preAllocatedVUs: preAllocatedVUs,
        maxVUs: maxVUs,
        tags: { phase: 'warmup' },
        gracefulStop: '5s',
      },
      measure: {
        executor: 'constant-arrival-rate',
        rate: RATE,
        timeUnit: '1s',
        duration: DURATION,
        startTime: WARMUP,
        preAllocatedVUs: preAllocatedVUs,
        maxVUs: maxVUs,
        tags: { phase: 'measure' },
        gracefulStop: '10s',
      },
    },
    // Thresholds read the measure phase only; warmup numbers are discarded.
    thresholds: {
      'http_req_failed{phase:measure}': [{ threshold: 'rate<0.01', abortOnFail: false }],
      'http_req_duration{phase:measure}': [`p(99)<${sla}`],
      // Scoped to the measured phase: a few drops while the VU pool is still
      // allocating during warmup are harmless, but a single drop during
      // measurement means the generator failed to offer the target rate and
      // the run is not the open-model test it claims to be.
      'dropped_iterations{scenario:measure}': ['count<1'],
      // Declared only so k6 materialises the submetric. Without it the request
      // count covers warmup and measurement together, which double-counts
      // against percentiles that are scoped to measurement alone.
      'http_reqs{phase:measure}': ['count>0'],
    },
  };

  return {
    options,
    params: { timeout: `${timeout}ms` },
    preAllocatedVUs,
    maxVUs,
    clampedFrom: clamped ? wanted : 0,
  };
}

/**
 * One line, once per run, saying what the generator committed to. Printed from
 * a scenario's setup() so it lands in the runner's log beside the result: a
 * cell sized against a clamp needs to say so on the record, not be inferred
 * from a drop count afterwards.
 */
export function announce(plan) {
  const gb = (n) => (n * 2 / 1024).toFixed(1);
  console.log(`  VUs               ${plan.preAllocatedVUs} pre-allocated, ` +
              `${plan.maxVUs} max (~${gb(plan.maxVUs)}GB at 2MB/VU)`);
  if (plan.clampedFrom) {
    console.log(`  VU BUDGET         maxVUs clamped from ${plan.clampedFrom}. ` +
                `If this cell saturates it will drop iterations and be ` +
                `marked INVALID rather than exhaust the generator.`);
  }
}

/** Writes the raw summary next to the run's other artefacts. */
export function summary(data) {
  const out = __ENV.OUT;
  const result = { stdout: textSummary(data) };
  if (out) {
    result[out] = JSON.stringify(data, null, 2);
  }
  return result;
}

// k6 divides a submetric's count by the whole test duration, warmup included,
// so its rate understates a measure-scoped count. Derive it from the measured
// window instead.
function durationSeconds(spec) {
  const m = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(String(spec).trim());
  if (!m) return NaN;
  const n = Number(m[1]);
  return { ms: n / 1000, s: n, m: n * 60, h: n * 3600 }[m[2]];
}

function textSummary(data) {
  const m = data.metrics;
  const dur = m['http_req_duration{phase:measure}'] || m.http_req_duration || { values: {} };
  const failed = m['http_req_failed{phase:measure}'] || m.http_req_failed || { values: {} };
  const reqs = m['http_reqs{phase:measure}'] || m.http_reqs || { values: {} };
  const dropped = m.dropped_iterations || { values: { count: 0 } };
  const v = dur.values || {};
  const count = reqs.values.count || 0;
  const secs = durationSeconds(DURATION);
  const achieved = Number.isFinite(secs) && secs > 0 ? count / secs : NaN;
  return [
    '',
    `  offered rate      ${RATE} rps`,
    `  measured for      ${DURATION} (after ${WARMUP} discarded)`,
    `  completed         ${count.toFixed(0)}${Number.isFinite(achieved) ? ` (${achieved.toFixed(1)} rps)` : ''}`,
    `  dropped           ${dropped.values.count || 0}`,
    `  error rate        ${(((failed.values.rate) || 0) * 100).toFixed(2)}%`,
    `  p50 / p95 / p99   ${fmt(v['p(50)'])} / ${fmt(v['p(95)'])} / ${fmt(v['p(99)'])} ms`,
    `  max               ${fmt(v.max)} ms`,
    '',
  ].join('\n');
}

function fmt(n) {
  return (n === undefined || n === null) ? '-' : n.toFixed(1);
}
