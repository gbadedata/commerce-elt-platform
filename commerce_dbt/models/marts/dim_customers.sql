{# Names and email addresses stay in staging: reporting users read marts only. #}
select
    customer_id,
    country,
    created_at,
    batch_id
from {{ ref('int_customers_checked') }}
where reject_reason is null
