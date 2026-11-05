select
    try_cast(src_row_id as integer) as src_row_id,
    order_id,
    customer_id,
    status,
    channel,
    created_at as created_at_raw,
    try_cast(created_at as timestamp) as created_at,
    try_cast(updated_at as timestamp) as updated_at,
    _batch_id as batch_id
from {{ source('raw', 'orders') }}
