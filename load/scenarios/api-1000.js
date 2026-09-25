// The long-wait workload at one second, where offered rate and in-flight count
// are the same number: 1,000 rps is 1,000 requests in flight, 2,000 rps is
// 2,000. Same shape as api.js otherwise - one downstream call, no database.
//
// Running this beside api-800.js gives two points on the same curve, so the
// cost of holding a waiting request can be read as a slope rather than guessed
// from a single measurement.
//
// mvc-platform is not a candidate here. 200 Tomcat threads over a one-second
// hold cap it at 200 rps, below the bottom rung, so every cell would be the
// same saturation result.
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, workload, announce, summary } from '../lib/common.js';

// timeoutMs: the 1,000ms default is BELOW this workload's healthy latency and
// would fail every single request.
// slaMs: delay + 300ms, the same budget /api gets at 200 + 300.
// vuMargin: 1.3, not the default 4. Healthy concurrency is already the large
// number here, and 4x it would ask the generator for ~8,000 VUs at 2,000 rps -
// about 16GB, well past the 8GiB generator.
const plan = workload({ latencyMs: 1010, timeoutMs: 2500, slaMs: 1300, vuMargin: 1.3 });

export const options = plan.options;

export function setup() {
  announce(plan);
}

export default function () {
  const res = http.get(`${BASE_URL}/api-1000`, plan.params);
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function handleSummary(data) {
  return summary(data);
}
