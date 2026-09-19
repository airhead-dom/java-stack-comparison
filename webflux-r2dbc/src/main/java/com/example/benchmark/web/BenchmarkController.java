package com.example.benchmark.web;

import java.time.OffsetDateTime;

import com.example.benchmark.api.AccountSummary;
import com.example.benchmark.api.Pong;
import com.example.benchmark.api.UpstreamResponse;
import com.example.benchmark.sql.BenchmarkQueries;
import io.r2dbc.spi.Readable;
import reactor.core.publisher.Mono;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;

/**
 * The same four workloads as the blocking variants, issuing byte-identical SQL
 * from {@link BenchmarkQueries} and mapping rows by hand for the same reason.
 */
@RestController
public class BenchmarkController {

	private final DatabaseClient databaseClient;

	private final WebClient upstreamClient;

	private final String variant;

	private final long upstreamDelayMs;

	public BenchmarkController(DatabaseClient databaseClient, WebClient upstreamClient,
			@Value("${spring.application.name}") String variant,
			@Value("${benchmark.upstream.delay-ms}") long upstreamDelayMs) {
		this.databaseClient = databaseClient;
		this.upstreamClient = upstreamClient;
		this.variant = variant;
		this.upstreamDelayMs = upstreamDelayMs;
	}

	@GetMapping("/nodb")
	public Mono<Pong> nodb() {
		return Mono.just(new Pong(this.variant, System.currentTimeMillis()));
	}

	@GetMapping("/db")
	public Mono<AccountSummary> db(@RequestParam long accountId) {
		return query(BenchmarkQueries.ACCOUNT_SUMMARY, accountId);
	}

	@GetMapping("/db-slow")
	public Mono<AccountSummary> dbSlow(@RequestParam long accountId) {
		return query(BenchmarkQueries.ACCOUNT_SUMMARY_SLOW, accountId);
	}

	@GetMapping("/api")
	public Mono<UpstreamResponse> api() {
		return this.upstreamClient.get()
				.uri(builder -> builder.path("/upstream")
						.queryParam("delayMs", this.upstreamDelayMs)
						.build())
				.retrieve()
				.bodyToMono(UpstreamResponse.class);
	}

	private Mono<AccountSummary> query(String sql, long accountId) {
		return this.databaseClient.sql(sql)
				.bind("accountId", accountId)
				.map(BenchmarkController::mapSummary)
				.one()
				.switchIfEmpty(Mono.error(() -> new ResponseStatusException(HttpStatus.NOT_FOUND)));
	}

	private static AccountSummary mapSummary(Readable row) {
		OffsetDateTime openedAt = row.get("opened_at", OffsetDateTime.class);
		return new AccountSummary(
				row.get("account_id", Long.class),
				row.get("account_number", String.class),
				row.get("product_type", String.class),
				row.get("currency", String.class),
				row.get("current_balance", java.math.BigDecimal.class),
				row.get("available_balance", java.math.BigDecimal.class),
				row.get("status", String.class),
				row.get("branch_code", String.class),
				openedAt != null ? openedAt.toInstant() : null,
				row.get("customer_id", Long.class),
				row.get("full_name", String.class),
				row.get("id_type", String.class),
				row.get("id_number", String.class));
	}
}
