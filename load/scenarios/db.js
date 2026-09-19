// One cheap database operation (~1ms connection hold). The pool has so much
// headroom here that it never binds; this isolates per-request overhead.
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, buildOptions, PARAMS, randomAccountId, summary } from '../lib/common.js';

export const options = buildOptions(5);

export default function () {
  const res = http.get(`${BASE_URL}/db?accountId=${randomAccountId()}`, PARAMS);
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function handleSummary(data) {
  return summary(data);
}
