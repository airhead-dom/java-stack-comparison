package com.example.benchmark.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

public record CustomerJob(
		Long id,
		Long customerId,
		String employmentStatus,
		String employerName,
		String occupation,
		String industry,
		BigDecimal monthlyIncome,
		LocalDate startDate,
		LocalDate endDate,
		boolean isCurrent,
		Instant createdAt) {
}
