"""End-to-end checks on DuckDB. Each rule is seen both passing and failing.

Run with: pytest -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import dq_results  # noqa: E402
import warehouse  # noqa: E402

DBT_DIR = ROOT / "commerce_dbt"
REPORTS = ROOT / "reports"
PLANTED_RULE_COUNT = 17


def pipeline(mode: str) -> int:
    command = [sys.executable, ROOT / "scripts" / "run_pipeline.py", "--mode", mode, "--target", "duckdb"]
    return subprocess.run([str(c) for c in command], capture_output=True, text=True).returncode


def dbt_test(selector: str, *extra: str) -> dict:
    env = {**os.environ, "DUCKDB_PATH": str(warehouse.DUCKDB_PATH)}
    command = ["dbt", "test", "--profiles-dir", ".", "--target", "duckdb", "--quiet", "--select", selector, *extra]
    subprocess.run(command, cwd=DBT_DIR, env=env, capture_output=True, text=True)
    result = json.loads((DBT_DIR / "target" / "run_results.json").read_text())["results"]
    assert len(result) == 1, f"{selector} selected {len(result)} tests"
    return result[0]


def report() -> dict:
    return json.loads((REPORTS / "dq_results.json").read_text())


def execute(sql: str) -> list[tuple]:
    conn = warehouse.connect("duckdb")
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


class TestCleanData:
    @pytest.fixture(scope="class", autouse=True)
    @classmethod
    def run(cls):
        cls.exit_code = pipeline("clean")

    def test_no_rule_fires_and_health_is_zero(self):
        data = report()
        assert [r["rule_id"] for r in data["rules"] if r["status"] != "pass"] == []
        assert data["overall_status"] == "HEALTHY"
        assert self.exit_code == 0

    def test_nothing_is_quarantined(self):
        assert report()["quarantine"] == []


class TestPlantedDefects:
    @pytest.fixture(scope="class", autouse=True)
    @classmethod
    def run(cls):
        cls.exit_code = pipeline("defects")

    def test_critical_defects_give_exit_code_two(self):
        assert report()["overall_status"] == "FAIL"
        assert self.exit_code == 2

    def test_every_planted_rule_finds_exactly_its_rows(self):
        evaluation = json.loads((REPORTS / "rule_evaluation.json").read_text())
        assert len(evaluation["rules"]) == PLANTED_RULE_COUNT
        for rule in evaluation["rules"]:
            assert rule["planted"] > 0, rule
            assert rule["false_positives"] == 0, rule
            assert rule["false_negatives"] == 0, rule

    def test_evaluation_can_report_a_miss_and_a_false_alarm(self):
        path = ROOT / "data" / "raw" / "defect_manifest.json"
        backup = path.with_suffix(".bak")
        shutil.copy(path, backup)
        try:
            manifest = json.loads(path.read_text())
            ids = manifest["rules"]["ORD_ID_UNIQUE"]
            dropped = ids.pop()
            ids.append(999_999_999)
            path.write_text(json.dumps(manifest))
            subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_rules.py")], check=True, capture_output=True)
            result = json.loads((REPORTS / "rule_evaluation.json").read_text())
            rule = next(r for r in result["rules"] if r["rule_id"] == "ORD_ID_UNIQUE")
            assert (rule["false_positives"], rule["false_negatives"]) == (1, 1), dropped
        finally:
            shutil.move(backup, path)
            subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_rules.py")], check=True, capture_output=True)

    def test_marts_stay_trusted_when_staging_has_defects(self):
        gates = [r for r in report()["rules"] if r["rule_id"].startswith(("GATE_", "RECON_"))]
        assert len(gates) == 9
        assert all(r["status"] == "pass" for r in gates)

    def test_every_rejected_row_has_a_reason(self):
        assert execute("select count(*) from monitoring.quarantine_rows where reject_reason is null")[0][0] == 0

    def test_personal_data_stays_out_of_marts_and_failure_tables(self):
        manifest = json.loads((DBT_DIR / "target" / "manifest.json").read_text())
        personal = {
            name.lower()
            for node in manifest["nodes"].values()
            for name, column in node.get("columns", {}).items()
            if (column.get("meta") or column.get("config", {}).get("meta") or {}).get("pii")
        }
        assert personal, "no column is tagged as personal data, so this test would prove nothing"
        columns = execute(
            """
            select table_schema, table_name, lower(column_name) from information_schema.columns
            where table_schema in ('marts', 'monitoring')
            """
        )
        assert [c for c in columns if c[2] in personal] == []

    def test_glossary_points_at_real_columns(self):
        glossary = yaml.safe_load((ROOT / "governance" / "business_glossary.yml").read_text())
        schemas = {"quarantine_rows": "monitoring"}
        for term in glossary["terms"]:
            model, column = term["location"].split(".")
            execute(f"select {column} from {schemas.get(model, 'marts')}.{model} limit 0")
            assert term["owner"] and term["definition"]

    def test_catalog_lists_an_owner_for_every_model(self):
        catalog = (ROOT / "docs" / "data_catalog.md").read_text()
        assert "UNASSIGNED" not in catalog

    def test_volume_rule_fails_when_threshold_is_not_met(self):
        outcome = dbt_test("config.meta.rule_id:ORD_MIN_VOLUME", "--vars", "{dq_orders_min_rows: 99999999}")
        assert outcome["status"] == "warn"

    def test_freshness_rule_fails_on_a_stale_load(self):
        outcome = dbt_test("config.meta.rule_id:FRESH_RAW_LOAD", "--vars", "{dq_max_load_age_hours: -1}")
        assert outcome["status"] == "warn"

    def test_unique_gate_stops_a_duplicate_reaching_a_mart(self):
        conn = warehouse.connect("duckdb")
        conn.execute("insert into marts.dim_customers select * from marts.dim_customers limit 1")
        conn.close()
        assert dbt_test("config.meta.rule_id:GATE_DIM_CUSTOMER_KEY_UNIQUE")["status"] == "fail"

    def test_reconciliation_fails_when_a_row_disappears(self):
        conn = warehouse.connect("duckdb")
        conn.execute(
            """
            delete from marts.fct_order_items
            where order_item_id = (select min(order_item_id) from marts.fct_order_items where net_amount > 0)
            """
        )
        conn.close()
        assert dbt_test("config.meta.rule_id:RECON_ROW_COUNTS")["status"] == "fail"
        assert dbt_test("config.meta.rule_id:RECON_ORDER_VALUE")["status"] == "fail"


class TestUnverifiedIsNotClean:
    def test_missing_results_make_every_rule_unverified(self, tmp_path):
        shutil.copy(DBT_DIR / "target" / "manifest.json", tmp_path / "manifest.json")
        rules = dq_results.rules_from_artifacts(tmp_path)
        assert rules and all(r["status"] == "unverified" for r in rules)
        assert dq_results.overall_status(rules) == "FAIL"

    @pytest.mark.parametrize(
        ("rules", "expected"),
        [
            ([{"status": "pass", "dq_severity": "critical"}], "HEALTHY"),
            ([{"status": "fail", "dq_severity": "warning"}], "WARN"),
            ([{"status": "fail", "dq_severity": "critical"}], "FAIL"),
            ([{"status": "unverified", "dq_severity": "warning"}], "FAIL"),
        ],
    )
    def test_overall_status(self, rules, expected):
        assert dq_results.overall_status(rules) == expected
