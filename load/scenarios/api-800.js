// The long-wait workload. Same shape as api.js - one downstream call, no
// database - but held for 800ms instead of 200ms.
//
// The point is in-flight concurrency, not thread count. At 1,000 rps this puts
// ~800 requests in flight; at 2,000 rps, ~1,600. Both are far past any thread
// count either candidate has, so what is measured is what a stack spends to
// hold a request that is waiting: heap, bookkeeping, and sockets.
//
// mvc-platform is not a candidate here. 200 Tomcat threads over an 800ms hold
// cap it at 250 rps, below the bottom rung, so every cell would be the same
// saturation result.
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, workload, announce, summary } from '../lib/common.js';

// timeoutMs: the 1,000ms default leaves 190ms of headroom over an 810ms healthy
// latency, so an ordinary GC pause would be recorded as a failed request.
// slaMs: delay + 300ms, the same budget /api gets at 200 + 300.
// vuMargin: 1.3, not the default 4. Healthy concurrency is already the large
// number here, and 4x it would ask the generator for ~6,500 VUs at 2,000 rps.
const plan = workload({ latencyMs: 810, timeoutMs: 2000, slaMs: 1100, vuMargin: 1.3 });

export const options = plan.options;

export function setup() {
  announce(plan);
}

export default function () {
  const res = http.get(`${BASE_URL}/api-800`, plan.params);
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function handleSummary(data) {
  return summary(data);
}
