-- Dataset is intentionally small enough to sit in shared_buffers, so the
-- benchmark measures the application, not Postgres disk I/O.

insert into customers (name, email)
select 'customer-' || i, 'customer-' || i || '@example.test'
from generate_series(1, 10000) as i
on conflict do nothing;

insert into orders (customer_id, amount, status)
select (random() * 9999)::int + 1,
       (random() * 1000)::numeric(12, 2),
       (array['NEW', 'PAID', 'SHIPPED'])[(random() * 2)::int + 1]
from generate_series(1, 50000)
on conflict do nothing;
