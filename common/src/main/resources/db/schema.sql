-- Core banking schema for the benchmark.
--
-- Shaped for realistic query cost rather than completeness: row widths, index
-- selectivity and join depth are what drive the numbers being measured. Status
-- and type columns are plain text rather than Postgres enums so that JDBC and
-- R2DBC need identical mapping code -- a converter required by only one variant
-- would be a difference in the code under test.

create table if not exists customers (
    id                  bigserial primary key,
    id_type             text not null check (id_type in ('KTP', 'PASSPORT')),
    id_number           text not null,
    full_name           text not null,
    date_of_birth       date not null,
    mother_maiden_name  text not null,
    marital_status      text not null
                        check (marital_status in ('SINGLE', 'MARRIED', 'DIVORCED', 'WIDOWED')),
    email               text,
    phone               text,
    status              text not null default 'ACTIVE'
                        check (status in ('ACTIVE', 'INACTIVE', 'BLOCKED')),
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    constraint uq_customers_identity unique (id_type, id_number)
);

create table if not exists customer_addresses (
    id            bigserial primary key,
    customer_id   bigint not null references customers (id),
    address_type  text not null check (address_type in ('HOME', 'WORK', 'MAILING')),
    line1         text not null,
    line2         text,
    city          text not null,
    province      text not null,
    postal_code   text not null,
    country       text not null default 'ID',
    is_primary    boolean not null default false,
    created_at    timestamptz not null default now()
);

create index if not exists idx_addresses_customer on customer_addresses (customer_id);
-- Partial unique: one primary address per customer, enforced in the index.
create unique index if not exists uq_addresses_primary
    on customer_addresses (customer_id) where is_primary;

create table if not exists customer_jobs (
    id                 bigserial primary key,
    customer_id        bigint not null references customers (id),
    employment_status  text not null
                       check (employment_status in ('EMPLOYED', 'SELF_EMPLOYED',
                                                    'UNEMPLOYED', 'RETIRED', 'STUDENT')),
    employer_name      text,
    occupation         text,
    industry           text,
    monthly_income     numeric(18, 2),
    start_date         date,
    end_date           date,
    is_current         boolean not null default true,
    created_at         timestamptz not null default now()
);

create index if not exists idx_jobs_customer on customer_jobs (customer_id);

create table if not exists accounts (
    id                 bigserial primary key,
    account_number     text not null unique,
    customer_id        bigint not null references customers (id),
    product_type       text not null
                       check (product_type in ('SAVINGS', 'CHECKING', 'TIME_DEPOSIT', 'LOAN')),
    currency           char(3) not null default 'IDR',
    -- Money is never floating point.
    current_balance    numeric(18, 2) not null default 0,
    available_balance  numeric(18, 2) not null default 0,
    status             text not null default 'ACTIVE'
                       check (status in ('ACTIVE', 'DORMANT', 'FROZEN', 'CLOSED')),
    branch_code        text not null,
    opened_at          timestamptz not null default now(),
    closed_at          timestamptz,
    created_by         text not null,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

create index if not exists idx_accounts_customer on accounts (customer_id);
create index if not exists idx_accounts_status on accounts (status, product_type);

create table if not exists transactions (
    id                    bigserial primary key,
    reference_number      text not null unique,
    account_id            bigint not null references accounts (id),
    direction             text not null check (direction in ('DEBIT', 'CREDIT')),
    transaction_type      text not null
                          check (transaction_type in ('TRANSFER', 'PAYMENT', 'WITHDRAWAL',
                                                      'DEPOSIT', 'FEE', 'INTEREST')),
    amount                numeric(18, 2) not null check (amount > 0),
    running_balance       numeric(18, 2),
    currency              char(3) not null default 'IDR',
    status                text not null
                          check (status in ('PENDING', 'POSTED', 'REVERSED', 'FAILED')),
    channel               text check (channel in ('ATM', 'MOBILE', 'TELLER', 'INTERNET', 'API')),
    counterparty_account  text,
    counterparty_name     text,
    description           text,
    posted_at             timestamptz,
    created_at            timestamptz not null default now()
);

-- The index the statement query lives on. Descending matches "most recent
-- N transactions for an account", which is the read the /fast and /slow
-- workloads are built around.
create index if not exists idx_transactions_account_posted
    on transactions (account_id, posted_at desc);
create index if not exists idx_transactions_created on transactions (created_at desc);
