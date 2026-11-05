"""Measure each rule against the planted-defect manifest.

This tests the rules, not the data. Planted defects are easy on purpose, so a perfect
score shows the rules fire on the right rows and nothing else. It says nothing about
defect types nobody thought to write a rule for.
"""

from __future__ import annotations

import argparse
import json
import sys

import warehouse

REPORTS = warehouse.ROOT / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=["duckdb", "snowflake"], default="duckdb")
    args = parser.parse_args()

    manifest = json.loads((warehouse.ROOT / "data" / "raw" / "defect_manifest.json").read_text())
    planted = manifest["rules"]
    report = json.loads((REPORTS / "dq_results.json").read_text())

    conn = warehouse.connect(args.target)
    evaluation = []
    try:
        for rule in report["rules"]:
            rule_id = rule["rule_id"]
            # Table-level rules and mart gates are not row-level, and are tested in pytest.
            if not rule_id.startswith(("CUST_", "PROD_", "ORD_", "ITEM_")) or rule_id == "ORD_MIN_VOLUME":
                continue
            if rule["status"] == "unverified":
                evaluation.append({"rule_id": rule_id, "planted": len(planted.get(rule_id, [])), "detected": 0,
                                   "true_positives": 0, "false_positives": 0,
                                   "false_negatives": len(planted.get(rule_id, []))})
                continue
            found = {
                int(r[0])
                for r in warehouse.rows(conn, f"select src_row_id from {rule['failure_relation']}")
                if r[0] is not None
            }
            expected = set(planted.get(rule_id, []))
            true_pos = len(found & expected)
            evaluation.append(
                {
                    "rule_id": rule_id,
                    "planted": len(expected),
                    "detected": len(found),
                    "true_positives": true_pos,
                    "false_positives": len(found - expected),
                    "false_negatives": len(expected - found),
                }
            )
    finally:
        conn.close()

    totals = {
        key: sum(e[key] for e in evaluation)
        for key in ("planted", "detected", "true_positives", "false_positives", "false_negatives")
    }
    totals["precision"] = round(totals["true_positives"] / totals["detected"], 4) if totals["detected"] else None
    totals["recall"] = round(totals["true_positives"] / totals["planted"], 4) if totals["planted"] else None
    output = {"mode": manifest["mode"], "seed": manifest["seed"], "totals": totals, "rules": evaluation}
    (REPORTS / "rule_evaluation.json").write_text(json.dumps(output, indent=2))
    print(
        f"mode={manifest['mode']} planted={totals['planted']} detected={totals['detected']} "
        f"false_positives={totals['false_positives']} false_negatives={totals['false_negatives']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
