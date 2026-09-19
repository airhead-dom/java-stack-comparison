package com.example.benchmark.entity;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class AccountEntity {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(name = "account_number")
	private String accountNumber;

	@Column(name = "product_type")
	private String productType;

	private String currency;

	@Column(name = "current_balance")
	private BigDecimal currentBalance;

	@Column(name = "available_balance")
	private BigDecimal availableBalance;

	private String status;

	@Column(name = "branch_code")
	private String branchCode;

	@Column(name = "opened_at")
	private Instant openedAt;

	// Lazy, and always fetched explicitly by the query. With open-in-view off
	// there is no session left to load it on demand, so a missing join fetch
	// fails loudly instead of quietly issuing a second statement.
	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "customer_id")
	private CustomerEntity customer;

	public Long getId() {
		return this.id;
	}

	public String getAccountNumber() {
		return this.accountNumber;
	}

	public String getProductType() {
		return this.productType;
	}

	public String getCurrency() {
		return this.currency;
	}

	public BigDecimal getCurrentBalance() {
		return this.currentBalance;
	}

	public BigDecimal getAvailableBalance() {
		return this.availableBalance;
	}

	public String getStatus() {
		return this.status;
	}

	public String getBranchCode() {
		return this.branchCode;
	}

	public Instant getOpenedAt() {
		return this.openedAt;
	}

	public CustomerEntity getCustomer() {
		return this.customer;
	}
}
