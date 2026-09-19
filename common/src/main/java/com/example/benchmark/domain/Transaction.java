package com.example.benchmark.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record Transaction(
		Long id,
		String referenceNumber,
		Long accountId,
		String direction,
		String transactionType,
		BigDecimal amount,
		BigDecimal runningBalance,
		String currency,
		String status,
		String channel,
		String counterpartyAccount,
		String counterpartyName,
		String description,
		Instant postedAt,
		Instant createdAt) {
}
