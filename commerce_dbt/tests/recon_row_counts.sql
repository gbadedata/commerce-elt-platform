{{ config(
    severity='error',
    alias='dqf_recon_row_counts',
    meta={
      'rule_id': 'RECON_ROW_COUNTS',
      'dimension': 'reconciliation',
      'dq_severity': 'critical',
      'owner': 'data-engineering',
      'description': 'Every raw row ends up in a mart or in quarantine, so no row is lost silently.'
    }
) }}

with raw_counts as (
    select 'customers' as entity, count(*) as raw_rows from {{ source('raw', 'customers') }}
    union all select 'products', count(*) from {{ source('raw', 'products') }}
    union all select 'orders', count(*) from {{ source('raw', 'orders') }}
    union all select 'order_items', count(*) from {{ source('raw', 'order_items') }}
),

valid_counts as (
    select 'customers' as entity, count(*) as valid_rows from {{ ref('dim_customers') }}
    union all select 'products', count(*) from {{ ref('dim_products') }}
    union all select 'orders', count(*) from {{ ref('int_orders_checked') }} where reject_reason is null
    union all select 'order_items', count(*) from {{ ref('fct_order_items') }}
),

quarantine_counts as (
    select entity, count(*) as quarantined_rows from {{ ref('quarantine_rows') }} group by entity
)

select
    cast(null as integer) as src_row_id,
    raw_counts.entity
from raw_counts
inner join valid_counts on raw_counts.entity = valid_counts.entity
left join quarantine_counts on raw_counts.entity = quarantine_counts.entity
where raw_counts.raw_rows <> valid_counts.valid_rows + coalesce(quarantine_counts.quarantined_rows, 0)
