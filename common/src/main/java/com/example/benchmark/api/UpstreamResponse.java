package com.example.benchmark.api;

/** What stub-service returns, and what the /api workload passes through. */
public record UpstreamResponse(long delayMs, String reference) {
}
