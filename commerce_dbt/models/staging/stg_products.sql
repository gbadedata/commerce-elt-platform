select
    try_cast(src_row_id as integer) as src_row_id,
    product_id,
    name as product_name,
    category,
    subcategory,
    try_cast(cost_price as decimal(12, 2)) as cost_price,
    try_cast(list_price as decimal(12, 2)) as list_price,
    _batch_id as batch_id
from {{ source('raw', 'products') }}
