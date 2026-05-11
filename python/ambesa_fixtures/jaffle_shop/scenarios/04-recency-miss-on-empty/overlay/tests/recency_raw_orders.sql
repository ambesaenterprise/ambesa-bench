-- Recency check on the orders source. Reproduces the post-fix shape from
-- dbt-labs/dbt-utils PR #1065 (commit e2add69, merged 2026-01-09):
-- a recency test must FAIL when the source has no data at all, not silently
-- pass. The pre-fix dbt-utils macro had a `WHERE max < threshold` clause
-- that evaluated to NULL on empty tables (NULL comparisons evaluate to
-- NULL, not TRUE), producing a zero-row result and an incorrectly-passing
-- test. The fix added `OR most_recent IS NULL`. This singular test
-- mirrors the post-fix behavior: an empty `raw_orders` table will fail.

with recency as (
    select max(cast(order_date as date)) as most_recent
    from {{ ref('stg_orders') }}
)

select most_recent
from recency
where most_recent < (current_date - interval '7' day)
   or most_recent is null
