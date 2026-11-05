with sequenced as (
    select
        *,
        row_number() over (partition by order_id order by src_row_id) as key_seq
    from {{ ref('stg_orders') }}
),

valid_customers as (
    select customer_id from {{ ref('int_customers_checked') }} where reject_reason is null
)

select
    orders.*,
    case
        when orders.key_seq > 1 then 'ORD_ID_UNIQUE'
        when orders.created_at is null then 'ORD_CREATED_PARSEABLE'
        when orders.customer_id is not null and valid_customers.customer_id is null then 'ORD_CUSTOMER_FK'
    end as reject_reason
from sequenced as orders
left join valid_customers
    on orders.customer_id = valid_customers.customer_id
