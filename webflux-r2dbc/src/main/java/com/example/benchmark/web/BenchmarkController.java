package com.example.benchmark.web;

import java.time.OffsetDateTime;

import com.example.benchmark.api.AccountStatement;
import com.example.benchmark.api.AccountSummary;
import com.example.benchmark.api.StatementAssembler;
import com.example.benchmark.api.StatementRow;
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

	private final long upstreamLongDelayMs;

	private final long upstreamLongestDelayMs;

	public BenchmarkController(DatabaseClient databaseClient, WebClient upstreamClient,
			@Value("${spring.application.name}") String variant,
			@Value("${benchmark.upstream.delay-ms}") long upstreamDelayMs,
			@Value("${benchmark.upstream.long-delay-ms}") long upstreamLongDelayMs,
			@Value("${benchmark.upstream.longest-delay-ms}") long upstreamLongestDelayMs) {
		this.databaseClient = databaseClient;
		this.upstreamClient = upstreamClient;
		this.variant = variant;
		this.upstreamDelayMs = upstreamDelayMs;
		this.upstreamLongDelayMs = upstreamLongDelayMs;
		this.upstreamLongestDelayMs = upstreamLongestDelayMs;
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

	@GetMapping("/db-heavy")
	public Mono<AccountStatement> dbHeavy(@RequestParam long accountId) {
		return this.databaseClient.sql(BenchmarkQueries.ACCOUNT_STATEMENT)
				.bind("accountId", accountId)
				.map(BenchmarkController::mapStatementRow)
				.all()
				.collectList()
				.flatMap((rows) -> rows.isEmpty()
						? Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND))
						: Mono.just(StatementAssembler.assemble(rows)));
	}

	@GetMapping("/api")
	public Mono<UpstreamResponse> api() {
		return call(this.upstreamDelayMs);
	}

	/**
	 * The same call held four times longer. At 1,000 rps that is ~800 requests
	 * in flight rather than ~200, which is past any thread count either stack
	 * has: what is scarce here is the memory and bookkeeping of a request in
	 * flight, not a worker to run it on.
	 */
	@GetMapping("/api-800")
	public Mono<UpstreamResponse> api800() {
		return call(this.upstreamLongDelayMs);
	}

	/** One second, so in-flight count and offered rate are the same number. */
	@GetMapping("/api-1000")
	public Mono<UpstreamResponse> api1000() {
		return call(this.upstreamLongestDelayMs);
	}

	// One request shape for all three delays, so the only thing that differs
	// between the endpoints is how long the upstream takes to answer.
	private Mono<UpstreamResponse> call(long delayMs) {
		return this.upstreamClient.get()
				.uri(builder -> builder.path("/upstream")
						.queryParam("delayMs", delayMs)
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

	private static StatementRow mapStatementRow(Readable row) {
		OffsetDateTime openedAt = row.get("opened_at", OffsetDateTime.class);
		OffsetDateTime postedAt = row.get("posted_at", OffsetDateTime.class);
		return new StatementRow(
				row.get("account_id", Long.class),
				row.get("account_number", String.class),
				row.get("product_type", String.class),
				row.get("currency", String.class),
				row.get("current_balance", java.math.BigDecimal.class),
				row.get("available_balance", java.math.BigDecimal.class),
				row.get("status", String.class),
				row.get("branch_code", String.class),
				(openedAt != null) ? openedAt.toInstant() : null,
				row.get("customer_id", Long.class),
				row.get("full_name", String.class),
				row.get("id_type", String.class),
				row.get("id_number", String.class),
				row.get("total_transactions", Long.class),
				row.get("total_debit", java.math.BigDecimal.class),
				row.get("total_credit", java.math.BigDecimal.class),
				row.get("transaction_id", Long.class),
				row.get("reference_number", String.class),
				row.get("direction", String.class),
				row.get("transaction_type", String.class),
				row.get("amount", java.math.BigDecimal.class),
				row.get("running_balance", java.math.BigDecimal.class),
				row.get("transaction_status", String.class),
				row.get("channel", String.class),
				row.get("counterparty_account", String.class),
				row.get("description", String.class),
				(postedAt != null) ? postedAt.toInstant() : null);
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
