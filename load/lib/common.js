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
  // in flight = rate x latency. Four times that leaves room for the queue to
  // grow during overload -- if k6 runs out of VUs it silently stops offering
  // the target rate and becomes a closed-model test without saying so.
  // Size for the SATURATED case, not the healthy one. Under overload latency
  // grows until it hits the timeout, so worst-case concurrency is rate x
  // timeout -- at 1,500 rps with healthy latency of 210ms a 4x margin looks
  // generous and is not: measured latency reached 1,333ms and the pool ran dry,
  // dropping a third of the offered load without the run failing.
  const maxVUs = Math.max(100, Math.ceil(RATE * (TIMEOUT_MS / 1000) * 1.2));
  // Allocate the whole pool up front. Growing it on demand costs time exactly
  // when the system is saturating and demand is climbing fastest, which is
  // when drops are least affordable. Memory is the trade: a VU costs a couple
  // of MB, so a 2,000-VU run wants a load generator with several GB free.
  const preAllocatedVUs = maxVUs;

  return {
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
      'http_req_duration{phase:measure}': [`p(99)<${SLA_MS}`],
      // Scoped to the measured phase: a few drops while the VU pool is still
      // allocating during warmup are harmless, but a single drop during
      // measurement means the generator failed to offer the target rate and
      // the run is not the open-model test it claims to be.
      'dropped_iterations{scenario:measure}': ['count<1'],
    },
  };
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

function textSummary(data) {
  const m = data.metrics;
  const dur = m['http_req_duration{phase:measure}'] || m.http_req_duration || { values: {} };
  const failed = m['http_req_failed{phase:measure}'] || m.http_req_failed || { values: {} };
  const reqs = m.http_reqs || { values: {} };
  const dropped = m.dropped_iterations || { values: { count: 0 } };
  const v = dur.values || {};
  return [
    '',
    `  offered rate      ${RATE} rps`,
    `  completed         ${(reqs.values.count || 0).toFixed(0)} (${(reqs.values.rate || 0).toFixed(1)} rps)`,
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
