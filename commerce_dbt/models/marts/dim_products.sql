select
    product_id,
    product_name,
    category,
    subcategory,
    cost_price,
    list_price,
    batch_id
from {{ ref('int_products_checked') }}
where reject_reason is null
