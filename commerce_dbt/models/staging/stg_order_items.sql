select
    try_cast(src_row_id as integer) as src_row_id,
    order_item_id,
    order_id,
    product_id,
    try_cast(quantity as integer) as quantity,
    try_cast(unit_price as decimal(12, 2)) as unit_price,
    try_cast(discount_amount as decimal(12, 2)) as discount_amount,
    _batch_id as batch_id
from {{ source('raw', 'order_items') }}
