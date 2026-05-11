# Scenario 01 — schema drift

## What's broken

Upstream renamed the primary key column in `raw_customers` from `id` to `customer_id`. The staging model `stg_customers.sql` still references the old name on line 14:

```sql
select
    id as customer_id,   -- ← `id` no longer exists in source
    first_name,
    last_name
from source
```

When `dbt build` runs against this scenario, `stg_customers` fails with something like:

```
Database Error in model stg_customers
  column "id" does not exist
```

Downstream models (`customers`, `orders`) fail in turn because their `ref('stg_customers')` is broken — total of 3+ failing nodes from one upstream rename.

## Expected diagnosis

```json
{
  "failure_class": "schema_drift",
  "root_cause": "raw_customers.id was renamed to customer_id upstream; stg_customers still references the old column.",
  "confidence": 0.85
}
```

## Expected fix

Update `models/staging/stg_customers.sql` line 14 from `id as customer_id,` to one of:

- `customer_id,`  (preferred — already had the alias on the right side)
- `customer_id as customer_id,`  (more verbose but explicit)

A grading script (week-1) checks for any rename of `id` → `customer_id` in the staging model.

## How the breakage was introduced

The overlay swaps the seed CSV header from `id,first_name,last_name` to `customer_id,first_name,last_name`. No other change.

## Files in this scenario

```
01-schema-drift/
├── README.md          (this file)
├── overlay/
│   └── seeds/
│       └── raw_customers.csv   # broken header
├── expected.json               # assertion target for diagnosis
├── expected.patch              # one acceptable fix shape
└── setup.sh                    # build runnable working dir
```
