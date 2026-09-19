package com.example.benchmark.api;

import java.math.BigDecimal;
import java.util.List;

/**
 * Response of the /db-heavy workload: an account statement. One database
 * operation, but real work -- two index scans over the account's transactions
 * and up to 20 mapped rows, rather than the single row /db returns.
 */
public record AccountStatement(
		AccountSummary account,
		long totalTransactions,
		BigDecimal totalDebit,
		BigDecimal totalCredit,
		List<TransactionLine> recentTransactions) {
}
