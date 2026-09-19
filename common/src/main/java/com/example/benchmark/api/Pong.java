package com.example.benchmark.api;

/** Response of the /nodb workload: no database, no upstream, no allocation. */
public record Pong(String variant, long served) {
}
