"""Exit 0 for HEALTHY, 1 for WARN and 2 for FAIL, so a scheduler or CI job can alert on it."""

from __future__ import annotations

import json
import sys

import warehouse


def main() -> int:
    report = json.loads((warehouse.ROOT / "reports" / "dq_results.json").read_text())
    for rule in report["rules"]:
        if rule["status"] != "pass":
            print(f"[{rule['status'].upper()}] {rule['rule_id']} ({rule['dq_severity']}, owner {rule['owner']}): "
                  f"{rule['failed_rows']} rows. {rule['description']}")
    status = report["overall_status"]
    print(f"Overall Status: {status}")
    return {"HEALTHY": 0, "WARN": 1, "FAIL": 2}[status]


if __name__ == "__main__":
    sys.exit(main())
