package com.example.benchmark.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummary(Long id, Long customerId, BigDecimal amount, String status, Instant createdAt) {}
