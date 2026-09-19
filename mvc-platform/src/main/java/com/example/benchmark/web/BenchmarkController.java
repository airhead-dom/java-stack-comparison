package com.example.benchmark.web;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;

import com.example.benchmark.api.AccountStatement;
import com.example.benchmark.api.AccountSummary;
import com.example.benchmark.api.StatementAssembler;
import com.example.benchmark.api.StatementRow;
import com.example.benchmark.api.Pong;
import com.example.benchmark.api.UpstreamResponse;
import com.example.benchmark.sql.BenchmarkQueries;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

/**
 * The four workloads. Rows are mapped by hand rather than by a mapping helper
 * so that this variant and the reactive one do the same amount of work -- an
 * automatic mapper on one side only would be a difference in the code measured.
 */
@RestController
public class BenchmarkController {

	private final JdbcClient jdbcClient;

	private final RestClient upstreamClient;

	private final String variant;

	private final long upstreamDelayMs;

	public BenchmarkController(JdbcClient jdbcClient, RestClient upstreamClient,
			@Value("${spring.application.name}") String variant,
			@Value("${benchmark.upstream.delay-ms}") long upstreamDelayMs) {
		this.jdbcClient = jdbcClient;
		this.upstreamClient = upstreamClient;
		this.variant = variant;
		this.upstreamDelayMs = upstreamDelayMs;
	}

	/** No database, no upstream: measures web-layer overhead alone. */
	@GetMapping("/nodb")
	public Pong nodb() {
		return new Pong(this.variant, System.currentTimeMillis());
	}

	/** One database operation, ~15ms of connection hold time. */
	@GetMapping("/db")
	public AccountSummary db(@RequestParam long accountId) {
		return query(BenchmarkQueries.ACCOUNT_SUMMARY, accountId);
	}

	/** The same single operation, holding its connection for ~100ms. */
	@GetMapping("/db-slow")
	public AccountSummary dbSlow(@RequestParam long accountId) {
		return query(BenchmarkQueries.ACCOUNT_SUMMARY_SLOW, accountId);
	}

	/**
	 * Still one database operation, but a realistic one: an aggregate over the
	 * account's whole history plus its twenty most recent transactions, and
	 * twenty rows to map instead of one.
	 */
	@GetMapping("/db-heavy")
	public AccountStatement dbHeavy(@RequestParam long accountId) {
		List<StatementRow> rows = this.jdbcClient.sql(BenchmarkQueries.ACCOUNT_STATEMENT)
				.param("accountId", accountId)
				.query(BenchmarkController::mapStatementRow)
				.list();
		if (rows.isEmpty()) {
			throw new ResponseStatusException(HttpStatus.NOT_FOUND);
		}
		return StatementAssembler.assemble(rows);
	}

	/**
	 * One downstream call and no database at all. Nothing here touches the
	 * connection pool, so whatever separates the variants is the thread model.
	 */
	@GetMapping("/api")
	public UpstreamResponse api() {
		return this.upstreamClient.get()
				.uri(builder -> builder.path("/upstream")
						.queryParam("delayMs", this.upstreamDelayMs)
						.build())
				.retrieve()
				.body(UpstreamResponse.class);
	}

	private AccountSummary query(String sql, long accountId) {
		return this.jdbcClient.sql(sql)
				.param("accountId", accountId)
				.query(BenchmarkController::mapSummary)
				.optional()
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
	}

	private static StatementRow mapStatementRow(ResultSet rs, int rowNum) throws SQLException {
		java.sql.Timestamp postedAt = rs.getTimestamp("posted_at");
		return new StatementRow(
				rs.getLong("account_id"),
				rs.getString("account_number"),
				rs.getString("product_type"),
				rs.getString("currency"),
				rs.getBigDecimal("current_balance"),
				rs.getBigDecimal("available_balance"),
				rs.getString("status"),
				rs.getString("branch_code"),
				rs.getTimestamp("opened_at").toInstant(),
				rs.getLong("customer_id"),
				rs.getString("full_name"),
				rs.getString("id_type"),
				rs.getString("id_number"),
				rs.getLong("total_transactions"),
				rs.getBigDecimal("total_debit"),
				rs.getBigDecimal("total_credit"),
				rs.getObject("transaction_id", Long.class),
				rs.getString("reference_number"),
				rs.getString("direction"),
				rs.getString("transaction_type"),
				rs.getBigDecimal("amount"),
				rs.getBigDecimal("running_balance"),
				rs.getString("transaction_status"),
				rs.getString("channel"),
				rs.getString("counterparty_account"),
				rs.getString("description"),
				(postedAt != null) ? postedAt.toInstant() : null);
	}

	private static AccountSummary mapSummary(ResultSet rs, int rowNum) throws SQLException {
		return new AccountSummary(
				rs.getLong("account_id"),
				rs.getString("account_number"),
				rs.getString("product_type"),
				rs.getString("currency"),
				rs.getBigDecimal("current_balance"),
				rs.getBigDecimal("available_balance"),
				rs.getString("status"),
				rs.getString("branch_code"),
				rs.getTimestamp("opened_at").toInstant(),
				rs.getLong("customer_id"),
				rs.getString("full_name"),
				rs.getString("id_type"),
				rs.getString("id_number"));
	}
}
