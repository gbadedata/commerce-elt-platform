{#
  The reusable rule library. Every rule returns one row per failing record, and only
  its src_row_id, so failure tables stay useful for triage without copying personal
  data out of staging. dbt stores the rows through store_failures.
#}

{% test dq_not_null(model, column_name) %}
select src_row_id from {{ model }}
where {{ column_name }} is null
{% endtest %}

{% test dq_unique(model, column_name) %}
select src_row_id from {{ model }}
where {{ column_name }} in (
    select {{ column_name }} from {{ model }}
    where {{ column_name }} is not null
    group by {{ column_name }}
    having count(*) > 1
)
{% endtest %}

{% test dq_accepted_values(model, column_name, values) %}
select src_row_id from {{ model }}
where {{ column_name }} is not null
  and {{ column_name }} not in (
    {%- for value in values %}'{{ value }}'{% if not loop.last %}, {% endif %}{% endfor -%}
  )
{% endtest %}

{% test dq_regex(model, column_name, pattern) %}
select src_row_id from {{ model }}
where {{ column_name }} is not null
  and not {{ dq_regex_match(column_name, pattern) }}
{% endtest %}

{% test dq_foreign_key(model, column_name, to, field) %}
select child.src_row_id
from {{ model }} as child
left join (select distinct {{ field }} as parent_key from {{ to }}) as parent
    on child.{{ column_name }} = parent.parent_key
where child.{{ column_name }} is not null
  and parent.parent_key is null
{% endtest %}

{% test dq_fail_when(model, condition) %}
select src_row_id from {{ model }}
where {{ condition }}
{% endtest %}

{% test dq_min_rows(model, min_rows) %}
select cast(null as integer) as src_row_id
from (select count(*) as row_count from {{ model }}) as totals
where row_count < {{ min_rows }}
{% endtest %}
