with sequenced as (
    select
        *,
        row_number() over (partition by customer_id order by src_row_id) as key_seq
    from {{ ref('stg_customers') }}
)

select
    *,
    case
        when customer_id is null then 'CUST_ID_NOT_NULL'
        when key_seq > 1 then 'CUST_ID_UNIQUE'
    end as reject_reason
from sequenced
