-- PLACEHOLDER SCHEMA. Replace with tables that resemble your real workload
-- before trusting any numbers: row width and index shape drive query cost.

create table if not exists customers (
    id      bigserial primary key,
    name    text not null,
    email   text not null unique
);

create table if not exists orders (
    id          bigserial primary key,
    customer_id bigint not null references customers (id),
    amount      numeric(12, 2) not null,
    status      text not null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_orders_customer on orders (customer_id);
