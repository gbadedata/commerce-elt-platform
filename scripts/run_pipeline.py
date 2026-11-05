"""Run the whole flow: generate, load, build, publish, evaluate, catalog, dashboard, health."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import warehouse

PY = sys.executable
SCRIPTS = warehouse.ROOT / "scripts"
DBT_DIR = warehouse.ROOT / "commerce_dbt"


def step(args: list, cwd=None, allow_failure: bool = False) -> int:
    print("\n$ " + " ".join(str(a) for a in args), flush=True)
    code = subprocess.run([str(a) for a in args], cwd=cwd).returncode
    if code and not allow_failure:
        sys.exit(code)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=["duckdb", "snowflake"], default="duckdb")
    parser.add_argument("--mode", choices=["clean", "defects"], default="defects")
    parser.add_argument("--scale", choices=["small", "full"], default="small")
    args = parser.parse_args()
    warehouse.load_env()
    if args.target == "duckdb" and warehouse.DUCKDB_PATH.exists():
        warehouse.DUCKDB_PATH.unlink()

    step([PY, SCRIPTS / "generate_data.py", "--mode", args.mode, "--scale", args.scale, "--out", warehouse.ROOT / "data" / "raw"])
    step([PY, SCRIPTS / "load_raw.py", "--target", args.target])
    # Results from an earlier run must never be read as this run's results.
    (DBT_DIR / "target" / "run_results.json").unlink(missing_ok=True)
    os.environ["DUCKDB_PATH"] = str(warehouse.DUCKDB_PATH)
    # A failed mart gate makes dbt exit non-zero. Results are still published, so the
    # failure appears in the report and the health check instead of stopping silently.
    dbt = step(["dbt", "build", "--profiles-dir", ".", "--target", args.target, "--quiet"], cwd=DBT_DIR, allow_failure=True)
    step([PY, SCRIPTS / "dq_results.py", "--target", args.target])
    step([PY, SCRIPTS / "evaluate_rules.py", "--target", args.target])
    step([PY, SCRIPTS / "export_catalog.py"])
    step([PY, SCRIPTS / "build_dashboard.py"])
    health = step([PY, SCRIPTS / "dq_health.py"], allow_failure=True)
    return max(health, 2 if dbt else 0)


if __name__ == "__main__":
    sys.exit(main())
