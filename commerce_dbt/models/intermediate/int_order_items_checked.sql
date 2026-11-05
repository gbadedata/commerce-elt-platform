with known_orders as (
    select distinct order_id from {{ ref('stg_orders') }}
),

known_products as (
    select distinct product_id from {{ ref('stg_products') }}
),

valid_orders as (
    select order_id, customer_id, status, channel, created_at
    from {{ ref('int_orders_checked') }}
    where reject_reason is null
),

valid_products as (
    select product_id from {{ ref('int_products_checked') }} where reject_reason is null
)

select
    items.*,
    valid_orders.customer_id,
    valid_orders.status as order_status,
    valid_orders.channel,
    valid_orders.created_at as order_created_at,
    case
        when known_orders.order_id is null then 'ITEM_ORDER_FK'
        when known_products.product_id is null then 'ITEM_PRODUCT_FK'
        when items.quantity <= 0 then 'ITEM_QTY_POSITIVE'
        when valid_orders.order_id is null then 'PARENT_ORDER_REJECTED'
        when valid_products.product_id is null then 'PARENT_PRODUCT_REJECTED'
    end as reject_reason
from {{ ref('stg_order_items') }} as items
left join known_orders on items.order_id = known_orders.order_id
left join known_products on items.product_id = known_products.product_id
left join valid_orders on items.order_id = valid_orders.order_id
left join valid_products on items.product_id = valid_products.product_id
