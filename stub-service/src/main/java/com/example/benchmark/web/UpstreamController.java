package com.example.benchmark.web;

import java.time.Duration;

import com.example.benchmark.api.UpstreamResponse;
import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Stands in for a downstream service with a controllable latency.
 *
 * Reactive and allocation-free on purpose: the /api workload puts hundreds of
 * requests in flight here at once, and this must never be the bottleneck. A
 * blocking sleep would need a thread per in-flight request and would measure
 * the stub rather than the system under test.
 */
@RestController
public class UpstreamController {

	private static final String REFERENCE = "UPSTREAM-OK";

	@GetMapping("/upstream")
	public Mono<UpstreamResponse> upstream(@RequestParam(defaultValue = "200") long delayMs) {
		return Mono.delay(Duration.ofMillis(delayMs))
				.map(tick -> new UpstreamResponse(delayMs, REFERENCE));
	}
}
