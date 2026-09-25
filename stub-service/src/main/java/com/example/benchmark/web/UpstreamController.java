package com.example.benchmark.web;

import java.time.Duration;

import com.example.benchmark.api.UpstreamResponse;
import reactor.core.publisher.Mono;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

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

	/**
	 * The longest delay any workload asks for is 1,000ms. Anything far beyond
	 * that is a typo in a generator script, and an unbounded value would park
	 * connections here for minutes while the run that caused it looked like a
	 * result. Fail loudly instead.
	 */
	private static final long MAX_DELAY_MS = 5000;

	@GetMapping("/upstream")
	public Mono<UpstreamResponse> upstream(@RequestParam(defaultValue = "200") long delayMs) {
		if (delayMs < 0 || delayMs > MAX_DELAY_MS) {
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
					"delayMs must be between 0 and " + MAX_DELAY_MS);
		}
		return Mono.delay(Duration.ofMillis(delayMs))
				.map(tick -> new UpstreamResponse(delayMs, REFERENCE));
	}
}
