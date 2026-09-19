-- Synthetic seed data. Volumes are set here in one place; raise them together
-- or the ratios stop resembling a real book of business.
--
--   customers     100,000
--   addresses     ~130,000  (every customer has HOME, 30% also have WORK)
--   jobs          100,000
--   accounts      ~150,000  (1-3 per customer)
--   transactions  2,000,000 (~13 per account)
--
-- Sized to sit in shared_buffers on the benchmark database instance, so the
-- measurement is the application and not Postgres disk I/O. If you raise these,
-- raise shared_buffers to match or the results describe your disk.

insert into customers (id_type, id_number, full_name, date_of_birth,
                       mother_maiden_name, marital_status, email, phone, status)
select
    case when i % 10 = 0 then 'PASSPORT' else 'KTP' end,
    case when i % 10 = 0
         then 'P' || lpad(i::text, 7, '0')
         else lpad((3171000000000000 + i)::text, 16, '0') end,
    'Customer ' || i,
    date '1950-01-01' + ((i * 7919) % 20000),
    (array['Wati', 'Sari', 'Dewi', 'Ningsih', 'Lestari', 'Rahayu'])[(i % 6) + 1],
    (array['SINGLE', 'MARRIED', 'MARRIED', 'DIVORCED', 'WIDOWED'])[(i % 5) + 1],
    'customer' || i || '@example.test',
    '08' || lpad(((i * 31) % 1000000000)::text, 10, '0'),
    case when i % 50 = 0 then 'INACTIVE' else 'ACTIVE' end
from generate_series(1, 100000) as i
on conflict do nothing;

insert into customer_addresses (customer_id, address_type, line1, city, province,
                                postal_code, is_primary)
select c.id, 'HOME',
       'Jl. Contoh No. ' || (c.id % 200 + 1),
       (array['Jakarta', 'Bandung', 'Surabaya', 'Medan', 'Makassar'])[(c.id % 5) + 1],
       (array['DKI Jakarta', 'Jawa Barat', 'Jawa Timur', 'Sumatera Utara',
              'Sulawesi Selatan'])[(c.id % 5) + 1],
       lpad(((c.id * 13) % 99999)::text, 5, '0'),
       true
from customers c
on conflict do nothing;

insert into customer_addresses (customer_id, address_type, line1, city, province,
                                postal_code, is_primary)
select c.id, 'WORK',
       'Gedung Contoh Lt. ' || (c.id % 30 + 1),
       (array['Jakarta', 'Bandung', 'Surabaya'])[(c.id % 3) + 1],
       (array['DKI Jakarta', 'Jawa Barat', 'Jawa Timur'])[(c.id % 3) + 1],
       lpad(((c.id * 17) % 99999)::text, 5, '0'),
       false
from customers c
where c.id % 10 < 3
on conflict do nothing;

insert into customer_jobs (customer_id, employment_status, employer_name, occupation,
                           industry, monthly_income, start_date, is_current)
select c.id,
       (array['EMPLOYED', 'EMPLOYED', 'SELF_EMPLOYED', 'RETIRED', 'STUDENT'])[(c.id % 5) + 1],
       'PT Contoh ' || (c.id % 500 + 1),
       (array['Staff', 'Supervisor', 'Manager', 'Engineer', 'Analyst'])[(c.id % 5) + 1],
       (array['Banking', 'Retail', 'Manufacturing', 'Technology', 'Education'])[(c.id % 5) + 1],
       ((c.id % 40) + 5) * 1000000.00,
       date '2010-01-01' + (((c.id * 13) % 5000))::int,
       true
from customers c
on conflict do nothing;

insert into accounts (account_number, customer_id, product_type, current_balance,
                      available_balance, status, branch_code, opened_at, created_by)
select
    lpad(((c.id * 10) + n)::text, 12, '0'),
    c.id,
    (array['SAVINGS', 'SAVINGS', 'CHECKING', 'TIME_DEPOSIT'])[((c.id + n) % 4) + 1],
    bal.v,
    bal.v,
    case when c.id % 40 = 0 then 'DORMANT' else 'ACTIVE' end,
    'BR' || lpad((c.id % 120 + 1)::text, 3, '0'),
    now() - ((c.id % 2000) || ' days')::interval,
    'SYSTEM_MIGRATION'
from customers c
cross join lateral generate_series(1, (c.id % 3) + 1) as n
cross join lateral (select (((c.id * 977 + n * 13) % 500000000) / 100.0)::numeric(18, 2)) as bal(v)
on conflict do nothing;

insert into transactions (reference_number, account_id, direction, transaction_type,
                          amount, running_balance, status, channel,
                          counterparty_account, description, posted_at)
select
    -- Globally unique: account id and row ordinal together, not the ordinal
    -- alone, or every account after the first collides.
    'TRX' || lpad(g.n::text, 14, '0'),
    a.id,
    case when g.n % 2 = 0 then 'DEBIT' else 'CREDIT' end,
    (array['TRANSFER', 'PAYMENT', 'WITHDRAWAL', 'DEPOSIT', 'FEE',
           'INTEREST'])[(g.n % 6) + 1],
    (((g.n * 7919) % 50000000) / 100.0 + 1)::numeric(18, 2),
    a.current_balance,
    case when g.n % 100 = 0 then 'PENDING' else 'POSTED' end,
    (array['ATM', 'MOBILE', 'TELLER', 'INTERNET', 'API'])[(g.n % 5) + 1],
    lpad(((g.n * 31) % 999999999999)::text, 12, '0'),
    'Seeded transaction ' || g.n,
    -- Spread over 90 days so the (account_id, posted_at desc) index is
    -- selective; a handful of distinct timestamps would make it useless.
    now() - (((g.n * 7919) % 90) || ' days')::interval
        - (((g.n * 31) % 86400) || ' seconds')::interval
from accounts a
cross join lateral generate_series(1, 13) as t(seq)
cross join lateral (select a.id * 13 + t.seq) as g(n)
on conflict do nothing;

-- Without this the planner has no statistics and will pick wrong plans on the
-- first runs, producing a warmup artifact that looks like a real result.
analyze customers;
analyze customer_addresses;
analyze customer_jobs;
analyze accounts;
analyze transactions;
