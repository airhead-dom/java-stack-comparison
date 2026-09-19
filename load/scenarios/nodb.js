// Web-layer overhead only: no database, no upstream. Control workload.
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, buildOptions, PARAMS, summary } from '../lib/common.js';

export const options = buildOptions(1);

export default function () {
  const res = http.get(`${BASE_URL}/nodb`, PARAMS);
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function handleSummary(data) {
  return summary(data);
}
