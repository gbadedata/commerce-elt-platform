"""Turn dbt artifacts into a data quality result per rule and publish the history.

A rule that exists in the project but has no result, or that errored, is reported
as ``unverified``. Unverified is never treated as clean.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import warehouse

TARGET_DIR = warehouse.ROOT / "commerce_dbt" / "target"
REPORTS = warehouse.ROOT / "reports"
RESULT_COLUMNS = [
    "run_id", "run_at", "rule_id", "dimension", "dq_severity", "owner", "description",
    "model", "status", "failed_rows", "rows_checked", "pass_rate",
]


def rules_from_artifacts(target_dir: Path = TARGET_DIR) -> list[dict]:
    manifest = json.loads((target_dir / "manifest.json").read_text())
    results_path = target_dir / "run_results.json"
    # No results file means dbt never finished, so every rule below becomes unverified.
    run_results = json.loads(results_path.read_text()) if results_path.exists() else {"results": []}
    outcomes = {r["unique_id"]: r for r in run_results["results"]}

    rules = []
    for node_id, node in manifest["nodes"].items():
        meta = node.get("config", {}).get("meta") or {}
        if node.get("resource_type") != "test" or "rule_id" not in meta:
            continue
        outcome = outcomes.get(node_id)
        attached = manifest["nodes"].get(node.get("attached_node") or "", {})
        evaluated = outcome is not None and outcome["status"] in {"pass", "warn", "fail"}
        failed = int(outcome.get("failures") or 0) if evaluated else None
        rules.append(
            {
                "rule_id": meta["rule_id"],
                "dimension": meta["dimension"],
                "dq_severity": meta["dq_severity"],
                "owner": meta["owner"],
                "description": meta["description"],
                "model": attached.get("name"),
                "model_relation": attached.get("relation_name"),
                "failure_relation": node.get("relation_name"),
                "status": "unverified" if not evaluated else ("fail" if failed else "pass"),
                "failed_rows": failed,
            }
        )
    return sorted(rules, key=lambda r: r["rule_id"])


def add_row_counts(conn, rules: list[dict]) -> None:
    counts: dict[str, int] = {}
    for rule in rules:
        relation = rule["model_relation"]
        rule["rows_checked"] = None
        rule["pass_rate"] = None
        if not relation or rule["status"] == "unverified":
            continue
        if relation not in counts:
            counts[relation] = warehouse.rows(conn, f"select count(*) from {relation}")[0][0]
        rule["rows_checked"] = counts[relation]
        if counts[relation] and rule["failed_rows"] is not None:
            rule["pass_rate"] = round(1 - rule["failed_rows"] / counts[relation], 6)


def overall_status(rules: list[dict]) -> str:
    """HEALTHY, WARN or FAIL. Critical failures and unverified rules both mean FAIL."""
    if any(r["status"] == "unverified" for r in rules):
        return "FAIL"
    if any(r["status"] == "fail" and r["dq_severity"] == "critical" for r in rules):
        return "FAIL"
    if any(r["status"] == "fail" for r in rules):
        return "WARN"
    return "HEALTHY"


def publish(conn, target: str, rules: list[dict], run_id: str, run_at: str) -> None:
    cur = conn.cursor()
    if target == "duckdb":
        # On Snowflake the schema comes from sql/setup/01_database_objects.sql.
        cur.execute("create schema if not exists monitoring")
    cur.execute(
        """
        create table if not exists monitoring.dq_results (
            run_id varchar, run_at varchar, rule_id varchar, dimension varchar, dq_severity varchar,
            owner varchar, description varchar, model varchar, status varchar,
            failed_rows integer, rows_checked integer, pass_rate double
        )
        """
    )
    marks = ", ".join([warehouse.placeholder(target)] * len(RESULT_COLUMNS))
    sql = f"insert into monitoring.dq_results ({', '.join(RESULT_COLUMNS)}) values ({marks})"
    for rule in rules:
        record = {"run_id": run_id, "run_at": run_at, **rule}
        cur.execute(sql, tuple(record[c] for c in RESULT_COLUMNS))
    # A stable view for Power BI, ThoughtSpot or a Snowflake alert to read.
    cur.execute(
        """
        create or replace view monitoring.v_dq_latest as
        select * from monitoring.dq_results
        where run_id = (select max(run_id) from monitoring.dq_results)
        """
    )


def quarantine_summary(conn) -> list[dict]:
    result = warehouse.rows(
        conn,
        """
        select entity, reject_reason, count(*)
        from monitoring.quarantine_rows
        group by entity, reject_reason
        order by entity, reject_reason
        """,
    )
    return [{"entity": e, "reject_reason": r, "rows": int(n)} for e, r, n in result]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=["duckdb", "snowflake"], default="duckdb")
    args = parser.parse_args()

    now = datetime.now(UTC).replace(microsecond=0)
    run_id = now.strftime("run_%Y%m%dT%H%M%S")
    conn = warehouse.connect(args.target)
    try:
        rules = rules_from_artifacts()
        add_row_counts(conn, rules)
        publish(conn, args.target, rules, run_id, now.isoformat())
        report = {
            "run_id": run_id,
            "run_at": now.isoformat(),
            "target": args.target,
            "overall_status": overall_status(rules),
            "rules": rules,
            "quarantine": quarantine_summary(conn) if any(r["status"] != "unverified" for r in rules) else [],
        }
    finally:
        conn.close()

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "dq_results.json").write_text(json.dumps(report, indent=2))
    failing = sum(r["status"] == "fail" for r in rules)
    print(f"{report['overall_status']}: {len(rules)} rules, {failing} failing, run {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
