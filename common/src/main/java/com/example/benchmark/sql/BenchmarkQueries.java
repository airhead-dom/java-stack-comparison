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
	 * One database operation, but genuinely heavy: two index scans over the
	 * account's transactions (an aggregate over all of them, and the most
	 * recent twenty) joined to the account and its customer. Returns up to 20
	 * rows rather than one, so result-set handling and object mapping are
	 * exercised as well as the round trip.
	 */
	public static final String ACCOUNT_STATEMENT = """
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
