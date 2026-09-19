package com.example.benchmark.api;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * One flattened row of the statement query. The header columns repeat on every
 * row; {@link StatementAssembler} folds them back into a nested response.
 *
 * This intermediate exists so all variants perform identical assembly work --
 * letting one of them use a framework's nested-result mapping and another do it
 * by hand would put a real difference inside the code under test.
 */
public record StatementRow(
		Long accountId,
		String accountNumber,
		String productType,
		String currency,
		BigDecimal currentBalance,
		BigDecimal availableBalance,
		String status,
		String branchCode,
		Instant openedAt,
		Long customerId,
		String customerName,
		String idType,
		String idNumber,
		long totalTransactions,
		BigDecimal totalDebit,
		BigDecimal totalCredit,
		Long transactionId,
		String referenceNumber,
		String direction,
		String transactionType,
		BigDecimal amount,
		BigDecimal runningBalance,
		String transactionStatus,
		String channel,
		String counterpartyAccount,
		String description,
		Instant postedAt) {
}
