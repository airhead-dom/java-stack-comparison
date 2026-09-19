// 100ms connection hold: the pool saturates at ~200 TPS, far below the 1,000
// target, so this workload is run on its own much lower ladder.
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, buildOptions, PARAMS, randomAccountId, summary } from '../lib/common.js';

export const options = buildOptions(110);

export default function () {
  const res = http.get(`${BASE_URL}/db-slow?accountId=${randomAccountId()}`, PARAMS);
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function handleSummary(data) {
  return summary(data);
}
