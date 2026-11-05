with sequenced as (
    select
        *,
        row_number() over (partition by product_id order by src_row_id) as key_seq
    from {{ ref('stg_products') }}
)

select
    *,
    case
        when key_seq > 1 then 'PROD_ID_UNIQUE'
        when cost_price <= 0 then 'PROD_COST_POSITIVE'
    end as reject_reason
from sequenced
