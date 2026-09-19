package com.example.benchmark.repository;

import java.util.Optional;

import com.example.benchmark.entity.AccountEntity;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AccountRepository extends JpaRepository<AccountEntity, Long> {

	/**
	 * Join fetch keeps this to a single statement, matching the one database
	 * operation the other variants perform. Without it, reading the customer
	 * would issue a second query and this variant would be doing more work.
	 */
	@Query("select a from AccountEntity a join fetch a.customer where a.id = :accountId")
	Optional<AccountEntity> findSummaryById(@Param("accountId") Long accountId);
}
