"""One small connection layer so the same scripts run on DuckDB and Snowflake."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUCKDB_PATH = Path(os.environ.get("DUCKDB_PATH", ROOT / "data" / "warehouse.duckdb")).resolve()
ENTITIES = ["customers", "products", "orders", "order_items"]


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def connect(target: str, role_env: str = "SNOWFLAKE_TRANSFORM_ROLE", wh_env: str = "SNOWFLAKE_TRANSFORM_WAREHOUSE"):
    """Return a DB-API style connection for the target."""
    if target == "duckdb":
        import duckdb

        DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(DUCKDB_PATH))
    if target == "snowflake":
        import snowflake.connector

        load_env()
        return snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            authenticator="SNOWFLAKE_JWT",
            private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
            role=os.environ[role_env],
            warehouse=os.environ[wh_env],
            database=os.environ.get("SNOWFLAKE_DATABASE", "COMMERCE_DB"),
        )
    raise ValueError(f"Unknown target: {target}")


def placeholder(target: str) -> str:
    return "?" if target == "duckdb" else "%s"


def rows(conn, sql: str, params: tuple | None = None) -> list[tuple]:
    cur = conn.cursor()
    cur.execute(sql, params) if params else cur.execute(sql)
    return [tuple(r) for r in cur.fetchall()]
