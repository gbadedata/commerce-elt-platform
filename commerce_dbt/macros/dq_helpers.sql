{# Current time in UTC as a plain timestamp. Snowflake sessions default to Los Angeles time. #}
{% macro dq_now() -%}
    {%- if target.type == 'snowflake' -%}
        convert_timezone('UTC', current_timestamp())::timestamp_ntz
    {%- else -%}
        cast(now() at time zone 'UTC' as timestamp)
    {%- endif -%}
{%- endmacro %}

{# Full-string regular expression match. REGEXP_LIKE in Snowflake is implicitly anchored. #}
{% macro dq_regex_match(column, pattern) -%}
    {%- if target.type == 'snowflake' -%}
        regexp_like({{ column }}, '{{ pattern }}')
    {%- else -%}
        regexp_full_match({{ column }}, '{{ pattern }}')
    {%- endif -%}
{%- endmacro %}
