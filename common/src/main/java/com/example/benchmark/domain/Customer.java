package com.example.benchmark.domain;

import java.time.Instant;
import java.time.LocalDate;

/**
 * Status and type columns are String rather than enum on purpose: an enum would
 * need a converter, and the converters differ between JDBC and R2DBC. That
 * difference would land in the code under test.
 */
public record Customer(
		Long id,
		String idType,
		String idNumber,
		String fullName,
		LocalDate dateOfBirth,
		String motherMaidenName,
		String maritalStatus,
		String email,
		String phone,
		String status,
		Instant createdAt,
		Instant updatedAt) {
}
