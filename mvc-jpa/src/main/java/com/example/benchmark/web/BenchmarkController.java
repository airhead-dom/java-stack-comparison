package com.example.benchmark.web;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

import com.example.benchmark.api.AccountSummary;
import com.example.benchmark.api.Pong;
import com.example.benchmark.api.UpstreamResponse;
import com.example.benchmark.entity.AccountEntity;
import com.example.benchmark.repository.AccountRepository;
import com.example.benchmark.sql.BenchmarkQueries;
import jakarta.persistence.EntityManager;
import jakarta.persistence.Tuple;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

/**
 * Control variant. Only /db exercises Hibernate's ORM path, which is the thing
 * this module exists to price: entity hydration, the persistence context, and
 * the join fetch that keeps it to one statement.
 *
 * /db-slow goes through a native query because pg_sleep has no JPQL equivalent,
 * so it measures Hibernate as a query executor rather than as an ORM. That is
 * acceptable here -- /db-slow is pool-bound and expected to look the same in
 * every variant -- but it is not evidence about ORM overhead.
 */
@RestController
public class BenchmarkController {

	private final AccountRepository accountRepository;

	private final EntityManager entityManager;

	private final RestClient upstreamClient;

	private final String variant;

	private final long upstreamDelayMs;

	public BenchmarkController(AccountRepository accountRepository, EntityManager entityManager,
			RestClient upstreamClient, @Value("${spring.application.name}") String variant,
			@Value("${benchmark.upstream.delay-ms}") long upstreamDelayMs) {
		this.accountRepository = accountRepository;
		this.entityManager = entityManager;
		this.upstreamClient = upstreamClient;
		this.variant = variant;
		this.upstreamDelayMs = upstreamDelayMs;
	}

	@GetMapping("/nodb")
	public Pong nodb() {
		return new Pong(this.variant, System.currentTimeMillis());
	}

	@GetMapping("/db")
	public AccountSummary db(@RequestParam long accountId) {
		AccountEntity account = this.accountRepository.findSummaryById(accountId)
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
		return new AccountSummary(
				account.getId(),
				account.getAccountNumber(),
				account.getProductType(),
				account.getCurrency(),
				account.getCurrentBalance(),
				account.getAvailableBalance(),
				account.getStatus(),
				account.getBranchCode(),
				account.getOpenedAt(),
				account.getCustomer().getId(),
				account.getCustomer().getFullName(),
				account.getCustomer().getIdType(),
				account.getCustomer().getIdNumber());
	}

	@GetMapping("/db-slow")
	public AccountSummary dbSlow(@RequestParam long accountId) {
		Tuple row;
		try {
			row = (Tuple) this.entityManager
					.createNativeQuery(BenchmarkQueries.ACCOUNT_SUMMARY_SLOW, Tuple.class)
					.setParameter("accountId", accountId)
					.getSingleResult();
		}
		catch (jakarta.persistence.NoResultException ex) {
			throw new ResponseStatusException(HttpStatus.NOT_FOUND);
		}
		return new AccountSummary(
				asLong(row.get("account_id")),
				(String) row.get("account_number"),
				(String) row.get("product_type"),
				(String) row.get("currency"),
				(BigDecimal) row.get("current_balance"),
				(BigDecimal) row.get("available_balance"),
				(String) row.get("status"),
				(String) row.get("branch_code"),
				asInstant(row.get("opened_at")),
				asLong(row.get("customer_id")),
				(String) row.get("full_name"),
				(String) row.get("id_type"),
				(String) row.get("id_number"));
	}

	@GetMapping("/api")
	public UpstreamResponse api() {
		return this.upstreamClient.get()
				.uri(builder -> builder.path("/upstream")
						.queryParam("delayMs", this.upstreamDelayMs)
						.build())
				.retrieve()
				.body(UpstreamResponse.class);
	}

	private static Long asLong(Object value) {
		return (value != null) ? ((Number) value).longValue() : null;
	}

	// Native queries hand back whichever temporal type the driver chose; fail
	// loudly on an unexpected one rather than returning something wrong.
	private static Instant asInstant(Object value) {
		return switch (value) {
			case null -> null;
			case Instant instant -> instant;
			case OffsetDateTime offsetDateTime -> offsetDateTime.toInstant();
			case Timestamp timestamp -> timestamp.toInstant();
			case LocalDateTime localDateTime -> localDateTime.toInstant(ZoneOffset.UTC);
			default -> throw new IllegalStateException(
					"unexpected temporal type: " + value.getClass().getName());
		};
	}
}
