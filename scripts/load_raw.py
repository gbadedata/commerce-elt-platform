"""Load the generated CSV files into RAW as untyped text, replacing the last batch.

Everything stays VARCHAR on purpose: a type error in a raw feed should become a
data quality finding in staging, not a failed load that hides the row.
"""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
from pathlib import Path

import warehouse


def header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


def load_duckdb(data_dir: Path, batch_id: str) -> dict[str, int]:
    conn = warehouse.connect("duckdb")
    conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
    counts = {}
    loaded_at = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    for entity in warehouse.ENTITIES:
        path = data_dir / f"{entity}.csv"
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE raw.{entity} AS
            SELECT *, ? AS _batch_id, ? AS _loaded_at
            FROM read_csv(?, header = true, all_varchar = true, nullstr = '')
            """,
            [batch_id, loaded_at, str(path)],
        )
        counts[entity] = conn.execute(f"SELECT count(*) FROM raw.{entity}").fetchone()[0]
    conn.close()
    return counts


def load_snowflake(data_dir: Path, batch_id: str) -> dict[str, int]:
    conn = warehouse.connect("snowflake", "SNOWFLAKE_LOAD_ROLE", "SNOWFLAKE_LOAD_WAREHOUSE")
    cur = conn.cursor()
    cur.execute("USE SCHEMA RAW")
    counts = {}
    try:
        for entity in warehouse.ENTITIES:
            path = data_dir / f"{entity}.csv"
            columns = header(path)
            ddl = ", ".join(f'"{c.upper()}" VARCHAR' for c in columns)
            cur.execute(
                f'CREATE OR REPLACE TABLE {entity} ({ddl}, "_BATCH_ID" VARCHAR, "_LOADED_AT" VARCHAR)'
            )
            cur.execute(f"PUT 'file://{path.resolve().as_posix()}' @%{entity} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
            positions = ", ".join(f"${i + 1}" for i in range(len(columns)))
            cur.execute(
                f"""
                COPY INTO {entity}
                FROM (
                    SELECT {positions}, '{batch_id}',
                           TO_VARCHAR(CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()), 'YYYY-MM-DD"T"HH24:MI:SS')
                    FROM @%{entity}
                )
                FILE_FORMAT = (FORMAT_NAME = 'COMMERCE_DB.RAW.CSV_FORMAT')
                ON_ERROR = 'ABORT_STATEMENT'
                """
            )
            counts[entity] = cur.execute(f"SELECT COUNT(*) FROM {entity}").fetchone()[0]
    finally:
        conn.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=["duckdb", "snowflake"], default="duckdb")
    parser.add_argument("--data-dir", type=Path, default=warehouse.ROOT / "data" / "raw")
    parser.add_argument("--batch-id", default=None)
    args = parser.parse_args()
    batch = args.batch_id or datetime.now(UTC).strftime("batch_%Y%m%dT%H%M%S")
    loader = load_duckdb if args.target == "duckdb" else load_snowflake
    print(f"batch={batch} loaded={loader(args.data_dir, batch)}")


if __name__ == "__main__":
    main()
