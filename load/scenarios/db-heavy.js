// The production-realistic database workload: statement query padded to a 15ms
// connection hold. Pool saturation sits at ~1,387 TPS, so the rate ladder
// crosses the knee.
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, buildOptions, PARAMS, randomAccountId, summary } from '../lib/common.js';

export const options = buildOptions(20);

export default function () {
  const res = http.get(`${BASE_URL}/db-heavy?accountId=${randomAccountId()}`, PARAMS);
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function handleSummary(data) {
  return summary(data);
}
