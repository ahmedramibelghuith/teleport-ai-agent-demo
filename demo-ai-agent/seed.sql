-- Demo dataset for the AI SRE agent: an "orders" table with a planted incident.
-- Story: a newly-added 'legacy_gateway' payment provider is slow and is stalling
-- checkouts in the last hour. The agent should discover this by querying.

DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
    order_id             SERIAL PRIMARY KEY,
    customer_email       TEXT NOT NULL,
    status               TEXT NOT NULL,        -- completed | pending_payment | failed
    amount_usd           NUMERIC(10,2) NOT NULL,
    payment_provider     TEXT NOT NULL,        -- stripe | paypal | legacy_gateway
    checkout_duration_ms INTEGER NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Healthy historical traffic over the past ~40 hours: fast checkouts via stripe/paypal.
INSERT INTO orders (customer_email, status, amount_usd, payment_provider, checkout_duration_ms, created_at)
SELECT
    'user' || g || '@example.com',
    'completed',
    round((random() * 180 + 20)::numeric, 2),
    (ARRAY['stripe', 'paypal'])[1 + (g % 2)],
    (random() * 400 + 150)::int,                       -- 150-550 ms: snappy
    now() - (g || ' hours')::interval
FROM generate_series(1, 40) g;

-- The last hour: the new 'legacy_gateway' provider is slow (8-14s) and many
-- orders are stuck in pending_payment -- this is the planted root cause.
INSERT INTO orders (customer_email, status, amount_usd, payment_provider, checkout_duration_ms, created_at)
SELECT
    'user' || (100 + g) || '@example.com',
    (ARRAY['pending_payment', 'pending_payment', 'completed', 'failed'])[1 + (g % 4)],
    round((random() * 180 + 20)::numeric, 2),
    'legacy_gateway',
    (random() * 6000 + 8000)::int,                     -- 8000-14000 ms: painful
    now() - ((g * 3) || ' minutes')::interval
FROM generate_series(1, 18) g;
