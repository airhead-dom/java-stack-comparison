// The decisive workload. No database at all, so nothing the connection pool
// does can explain the result: each request simply holds a thread for the
// duration of a 200ms upstream call. At 1,000 TPS that is ~200 in flight,
// exactly Tomcat's default thread count.
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, buildOptions, PARAMS, summary } from '../lib/common.js';

export const options = buildOptions(210);

export default function () {
  const res = http.get(`${BASE_URL}/api`, PARAMS);
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function handleSummary(data) {
  return summary(data);
}
