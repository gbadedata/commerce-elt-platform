{{ config(
    severity='error',
    alias='dqf_recon_order_value',
    meta={
      'rule_id': 'RECON_ORDER_VALUE',
      'dimension': 'reconciliation',
      'dq_severity': 'critical',
      'owner': 'finance-data',
      'description': 'Net value in the fact table plus quarantined value equals the value received, within 0.01.'
    }
) }}

with received as (
    select sum(quantity * unit_price - discount_amount) as value_received
    from {{ ref('stg_order_items') }}
),

accounted as (
    select sum(net_amount) as value_accounted
    from {{ ref('fct_order_items') }}
),

quarantined as (
    select coalesce(sum(quantity * unit_price - discount_amount), 0) as value_quarantined
    from {{ ref('int_order_items_checked') }}
    where reject_reason is not null
)

select cast(null as integer) as src_row_id
from received
cross join accounted
cross join quarantined
where abs(value_received - value_accounted - value_quarantined) > 0.01
