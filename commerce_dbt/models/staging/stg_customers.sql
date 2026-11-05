select
    try_cast(src_row_id as integer) as src_row_id,
    customer_id,
    email,
    first_name,
    last_name,
    country,
    created_at as created_at_raw,
    try_cast(created_at as timestamp) as created_at,
    _batch_id as batch_id
from {{ source('raw', 'customers') }}
