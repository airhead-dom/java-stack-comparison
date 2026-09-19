package com.example.benchmark.api;

import java.math.BigDecimal;
import java.time.Instant;

/** Response of the /db and /db-slow workloads. Identical in every variant. */
public record AccountSummary(
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
		String idNumber) {
}
