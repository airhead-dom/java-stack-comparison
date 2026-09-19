package com.example.benchmark.sql;

/**
 * The SQL under test, held here so every variant issues byte-identical
 * statements. Named parameters ({@code :accountId}) are used because Spring's
 * JdbcClient and R2DBC DatabaseClient both accept that form -- positional
 * markers differ between the two ({@code ?} versus {@code $1}) and would make
 * the statements no longer identical.
 */
public final class BenchmarkQueries {
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

	/**
	 * One database operation, genuinely heavy on the application side: two index
	 * scans over the account's transactions (an aggregate over all of them, and
	 * the most recent twenty) joined to the account and its customer, returning
	 * up to 20 rows to map rather than one.
	 *
	 * The leading sleep is a deliberate pad. Measured warm, this query holds a
	 * connection for ~1ms because twenty index-scanned rows cost Postgres
	 * almost nothing -- but production reports ~15ms, which is mostly network
	 * latency to a remote database plus contention that a local instance cannot
	 * reproduce. The pad stands in for exactly that, so pool occupancy matches
	 * production and the saturation knee lands at the designed 1,333 TPS.
	 *
	 * It is a stand-in, not real work: a sleeping connection burns no CPU and no
	 * I/O. Only pool behaviour is modelled faithfully by it. See
	 * docs/WORKLOADS.md.
	 */
	public static final String ACCOUNT_STATEMENT = """
			with pad as (select pg_sleep(0.011))
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
			       c.id_number      as id_number,
			       agg.total_transactions as total_transactions,
			       agg.total_debit  as total_debit,
			       agg.total_credit as total_credit,
			       t.id             as transaction_id,
			       t.reference_number as reference_number,
			       t.direction      as direction,
			       t.transaction_type as transaction_type,
			       t.amount         as amount,
			       t.running_balance as running_balance,
			       t.status         as transaction_status,
			       t.channel        as channel,
			       t.counterparty_account as counterparty_account,
			       t.description    as description,
			       t.posted_at      as posted_at
			from accounts a
			cross join pad
			join customers c on c.id = a.customer_id
			join lateral (
			    select count(*) as total_transactions,
			           coalesce(sum(amount) filter (where direction = 'DEBIT'), 0) as total_debit,
			           coalesce(sum(amount) filter (where direction = 'CREDIT'), 0) as total_credit
			    from transactions
			    where account_id = a.id
			) agg on true
			left join lateral (
			    select id, reference_number, direction, transaction_type, amount,
			           running_balance, status, channel, counterparty_account,
			           description, posted_at
			    from transactions
			    where account_id = a.id
			    order by posted_at desc
			    limit 20
			) t on true
			where a.id = :accountId
			""";

	private BenchmarkQueries() {
	}
}
