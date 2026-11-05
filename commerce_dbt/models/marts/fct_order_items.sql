select
    order_item_id,
    order_id,
    product_id,
    customer_id,
    order_status,
    channel,
    order_created_at,
    quantity,
    unit_price,
    discount_amount,
    cast(quantity * unit_price - discount_amount as decimal(14, 2)) as net_amount,
    batch_id
from {{ ref('int_order_items_checked') }}
where reject_reason is null
