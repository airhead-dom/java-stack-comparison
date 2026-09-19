package com.example.benchmark.sql;

/**
 * The SQL under test, held here so every variant issues byte-identical
 * statements. Named parameters ({@code :accountId}) are used because Spring's
 * JdbcClient and R2DBC DatabaseClient both accept that form -- positional
 * markers differ between the two ({@code ?} versus {@code $1}) and would make
 * the statements no longer identical.
 */
public final class BenchmarkQueries {

	/** One database operation: account joined to its owning customer. */
	public static final String ACCOUNT_SUMMARY = """
			select a.id             as account_id,
			       a.account_number as account_number,
			       a.product_type   as product_type,
			       a.currency       as currency,
			       a.current_balance   as current_balance,
			       a.available_balance as available_balance,
			       a.status         as status,
			       a.branch_code    as branch_code,
			       a.opened_at      as opened_at,
			       c.id             as customer_id,
			       c.full_name      as full_name,
			       c.id_type        as id_type,
			       c.id_number      as id_number
			from accounts a
			join customers c on c.id = a.customer_id
			where a.id = :accountId
			""";

	/**
	 * The same single operation, made to hold its connection for ~100ms. The
	 * sleep sits in a CTE rather than the select list so that no column of type
	 * void reaches the driver, which JDBC and R2DBC handle differently.
	 */
	public static final String ACCOUNT_SUMMARY_SLOW = """
			with delay as (select pg_sleep(0.1))
			select a.id             as account_id,
			       a.account_number as account_number,
			       a.product_type   as product_type,
			       a.currency       as currency,
			       a.current_balance   as current_balance,
			       a.available_balance as available_balance,
			       a.status         as status,
			       a.branch_code    as branch_code,
			       a.opened_at      as opened_at,
			       c.id             as customer_id,
			       c.full_name      as full_name,
			       c.id_type        as id_type,
			       c.id_number      as id_number
			from accounts a
			join customers c on c.id = a.customer_id
			cross join delay
			where a.id = :accountId
			""";

	private BenchmarkQueries() {
	}
}
