package com.example.benchmark.api;

import java.util.ArrayList;
import java.util.List;

/** Folds the flattened statement rows into the nested response. */
public final class StatementAssembler {

	public static AccountStatement assemble(List<StatementRow> rows) {
		StatementRow head = rows.getFirst();
		List<TransactionLine> lines = new ArrayList<>(rows.size());
		for (StatementRow row : rows) {
			// The left join yields a single null-transaction row for an account
			// with no history.
			if (row.transactionId() != null) {
				lines.add(new TransactionLine(
						row.transactionId(),
						row.referenceNumber(),
						row.direction(),
						row.transactionType(),
						row.amount(),
						row.runningBalance(),
						row.transactionStatus(),
						row.channel(),
						row.counterpartyAccount(),
						row.description(),
						row.postedAt()));
			}
		}
		AccountSummary account = new AccountSummary(
				head.accountId(), head.accountNumber(), head.productType(), head.currency(),
				head.currentBalance(), head.availableBalance(), head.status(), head.branchCode(),
				head.openedAt(), head.customerId(), head.customerName(), head.idType(),
				head.idNumber());
		return new AccountStatement(account, head.totalTransactions(), head.totalDebit(),
				head.totalCredit(), lines);
	}

	private StatementAssembler() {
	}
}
