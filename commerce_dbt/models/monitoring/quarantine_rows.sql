{# Rejected rows are kept and explained, never silently dropped. No personal data is copied here. #}
{% set entities = [
    ('customers', 'int_customers_checked'),
    ('products', 'int_products_checked'),
    ('orders', 'int_orders_checked'),
    ('order_items', 'int_order_items_checked')
] %}

{% for entity, model in entities %}
select
    '{{ entity }}' as entity,
    src_row_id,
    reject_reason,
    batch_id
from {{ ref(model) }}
where reject_reason is not null
{% if not loop.last %}union all{% endif %}
{% endfor %}
