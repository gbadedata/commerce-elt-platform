{# Use the schemas created in sql/setup/01_database_objects.sql exactly, with no prefix. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.schema) | trim }}
{%- endmacro %}
