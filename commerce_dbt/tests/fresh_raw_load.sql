{{ config(
    severity='warn',
    alias='dqf_fresh_raw_load',
    meta={
      'rule_id': 'FRESH_RAW_LOAD',
      'dimension': 'timeliness',
      'dq_severity': 'warning',
      'owner': 'data-engineering',
      'description': 'The latest raw batch arrived within the agreed window.'
    }
) }}

select cast(null as integer) as src_row_id
from (select max(try_cast(_loaded_at as timestamp)) as last_load from {{ source('raw', 'orders') }}) as latest
where last_load is null
   or {{ dbt.datediff('last_load', dq_now(), 'hour') }} > {{ var('dq_max_load_age_hours') }}
