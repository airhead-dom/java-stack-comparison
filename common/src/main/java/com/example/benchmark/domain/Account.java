package com.example.benchmark.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record Account(
		Long id,
		String accountNumber,
		Long customerId,
		String productType,
		String currency,
		BigDecimal currentBalance,
		BigDecimal availableBalance,
		String status,
		String branchCode,
		Instant openedAt,
		Instant closedAt,
		String createdBy,
		Instant createdAt,
		Instant updatedAt) {
}
