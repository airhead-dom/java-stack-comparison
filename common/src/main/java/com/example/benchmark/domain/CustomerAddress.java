package com.example.benchmark.domain;

import java.time.Instant;

public record CustomerAddress(
		Long id,
		Long customerId,
		String addressType,
		String line1,
		String line2,
		String city,
		String province,
		String postalCode,
		String country,
		boolean isPrimary,
		Instant createdAt) {
}
