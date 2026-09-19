package com.example.benchmark.api;

import java.math.BigDecimal;
import java.time.Instant;

public record TransactionLine(
		Long id,
		String referenceNumber,
		String direction,
		String transactionType,
		BigDecimal amount,
		BigDecimal runningBalance,
		String status,
		String channel,
		String counterpartyAccount,
		String description,
		Instant postedAt) {
}
