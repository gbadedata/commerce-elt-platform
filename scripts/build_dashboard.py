"""Write reports/dq_dashboard.html, a single file with no external dependencies."""

from __future__ import annotations

import html
import json
import sys
from collections import defaultdict

import warehouse

REPORTS = warehouse.ROOT / "reports"
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
ICONS = {
    "pass": ("good", "&#10003;", "Pass"),
    "warn": ("warning", "!", "Warning"),
    "fail": ("critical", "&#10005;", "Fail"),
    "unverified": ("serious", "?", "Not verified"),
}

CSS = """
:root{color-scheme:light dark;--bg:#fcfcfb;--panel:#fff;--ink:#0b0b0b;--muted:#52514e;--line:#e4e3de;
--track:#ecebe6;--bar:#2a78d6;--good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--panel:#232321;--ink:#f0efec;--muted:#c3c2b7;
--line:#3a3a37;--track:#30302d;--bar:#3987e5}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1120px;margin:0 auto;padding:32px 16px 56px}
h1{font-size:26px;line-height:1.2;margin:0 0 4px}
h2{font-size:17px;margin:0 0 4px}
.sub,.note{color:var(--muted);font-size:13px}
.note{margin:0 0 14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:22px 0}
.tile,section{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px}
.tile b{display:block;font-size:30px;line-height:1.2;font-variant-numeric:tabular-nums}
.tile span{color:var(--muted);font-size:13px}
section{margin-top:12px}
.row{display:grid;grid-template-columns:130px 1fr 74px;gap:10px;align-items:center;padding:7px 0}
.track{height:10px;background:var(--track);border-radius:4px;overflow:hidden}
.fill{height:100%;background:var(--bar);border-radius:0 4px 4px 0}
.row:hover .fill,.row:focus .fill{filter:brightness(1.15)}
.num{text-align:right;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:var(--muted);font-weight:600;border-bottom:1px solid var(--line);
padding:7px 10px 7px 0;white-space:nowrap}
td{border-bottom:1px solid var(--line);padding:8px 10px 8px 0;vertical-align:top}
td.num,th.num{text-align:right;padding-right:14px;white-space:nowrap}
table.rules{min-width:860px}
tr:last-child td{border-bottom:0}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace}
.status{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.dot{display:inline-grid;place-items:center;width:17px;height:17px;border-radius:50%;color:#fff;font-size:11px;font-weight:700}
.dot.good{background:var(--good)}.dot.warning{background:var(--warning);color:#0b0b0b}
.dot.serious{background:var(--serious);color:#0b0b0b}.dot.critical{background:var(--critical)}
.tip{position:fixed;display:none;max-width:280px;background:var(--ink);color:var(--bg);font-size:12.5px;
padding:7px 10px;border-radius:6px;pointer-events:none;z-index:5}
@media (max-width:640px){.row{grid-template-columns:96px 1fr 60px}}
"""

JS = """
const tip=document.querySelector('.tip');
function show(el,x,y){tip.textContent=el.dataset.tip;tip.style.display='block';
tip.style.left=Math.min(x+12,innerWidth-tip.offsetWidth-8)+'px';tip.style.top=(y+14)+'px'}
document.querySelectorAll('[data-tip]').forEach(el=>{
el.addEventListener('mousemove',e=>show(el,e.clientX,e.clientY));
el.addEventListener('mouseleave',()=>tip.style.display='none');
el.addEventListener('focus',()=>{const r=el.getBoundingClientRect();show(el,r.left,r.bottom)});
el.addEventListener('blur',()=>tip.style.display='none')});
"""


def esc(value) -> str:
    return html.escape(str(value))


def status_badge(key: str, label: str | None = None) -> str:
    tone, icon, default = ICONS[key]
    dot = f'<span class="dot {tone}" aria-hidden="true">{icon}</span>'
    return f'<span class="status">{dot}{esc(label or default)}</span>'


def render(report: dict, evaluation: dict | None) -> str:
    rules = report["rules"]
    failing = [r for r in rules if r["status"] == "fail"]
    unverified = [r for r in rules if r["status"] == "unverified"]
    quarantined = sum(q["rows"] for q in report["quarantine"])
    overall = {"HEALTHY": "pass", "WARN": "warn", "FAIL": "fail"}[report["overall_status"]]
    overall_label = {"HEALTHY": "Healthy", "WARN": "Warning", "FAIL": "Failing"}[report["overall_status"]]

    tiles = [
        (status_badge(overall, overall_label), f"Overall, {esc(report['target'])}"),
        (len(rules), "Rules evaluated"),
        (len(failing), "Rules with failures"),
        (len(unverified), "Rules not verified"),
        (f"{quarantined:,}", "Rows quarantined"),
    ]
    tile_html = "".join(f'<div class="tile"><b>{v}</b><span>{k}</span></div>' for v, k in tiles)

    groups = defaultdict(list)
    for rule in rules:
        groups[rule["dimension"]].append(rule)
    bars = []
    for dimension, members in sorted(groups.items()):
        label = dimension.replace("_", " ").capitalize()
        passed = sum(r["status"] == "pass" for r in members)
        share = passed / len(members)
        names = ", ".join(r["rule_id"] for r in members if r["status"] != "pass") or "none"
        bars.append(
            f'<div class="row" tabindex="0" data-tip="{esc(label)}: {passed} of {len(members)} rules pass. '
            f'Not passing: {esc(names)}"><span>{esc(label)}</span>'
            f'<div class="track"><div class="fill" style="width:{share * 100:.1f}%"></div></div>'
            f'<span class="num">{passed} of {len(members)}</span></div>'
        )

    ordered = sorted(rules, key=lambda r: (r["status"] == "pass", SEVERITY_ORDER.get(r["dq_severity"], 9), r["rule_id"]))
    detection = {e["rule_id"]: e for e in (evaluation or {}).get("rules", [])}
    rows = []
    for rule in ordered:
        key = "fail" if rule["status"] == "fail" and rule["dq_severity"] == "critical" else rule["status"]
        if rule["status"] == "fail" and rule["dq_severity"] != "critical":
            key = "warn"
        failed = "not known" if rule["failed_rows"] is None else f"{rule['failed_rows']:,}"
        rate = "" if rule["pass_rate"] is None else f"{rule['pass_rate'] * 100:.2f}%"
        found = detection.get(rule["rule_id"])
        planted = f"{found['true_positives']} of {found['planted']}" if found else ""
        rows.append(
            f"<tr><td>{status_badge(key)}</td><td><code>{esc(rule['rule_id'])}</code></td><td>{esc(rule['description'])}</td>"
            f"<td>{esc(rule['dq_severity'])}</td><td>{esc(rule['owner'])}</td><td class=num>{failed}</td>"
            f"<td class=num>{rate}</td><td class=num>{planted}</td></tr>"
        )

    q_rows = "".join(
        f"<tr><td>{esc(q['entity'])}</td><td><code>{esc(q['reject_reason'])}</code></td><td class=num>{q['rows']:,}</td></tr>"
        for q in report["quarantine"]
    ) or '<tr><td colspan="3">No rows quarantined.</td></tr>'

    if evaluation and evaluation["totals"]["planted"]:
        t = evaluation["totals"]
        check = (
            f"This run used synthetic data with {t['planted']} planted defects. The rules found "
            f"{t['true_positives']}, missed {t['false_negatives']} and wrongly flagged {t['false_positives']}. "
            "That shows the rules work as written. It does not show the data has no other kinds of problem."
        )
    else:
        check = "This run used synthetic data with no planted defects, so any failure would be a false alarm."

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Data Quality Dashboard</title>
<style>{CSS}</style></head><body><main>
<h1>Commerce data quality</h1>
<div class="sub">Run {esc(report['run_id'])}, {esc(report['run_at'])}</div>
<div class="tiles">{tile_html}</div>
<section><h2>Rules passing by dimension</h2><p class="note">{esc(check)}</p>{''.join(bars)}</section>
<section><h2>Rules</h2><p class="note">Sorted by what needs attention first. Planted shows defects found out of those planted.</p>
<div class="scroll" tabindex="0"><table class="rules"><thead><tr>
<th>Status</th><th>Rule</th><th>What it checks</th><th>Severity</th><th>Owner</th>
<th class=num>Failed rows</th><th class=num>Pass rate</th><th class=num>Planted</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<section><h2>Quarantine</h2><p class="note">Rows kept out of the marts, with the reason, so they can be fixed and replayed.</p>
<div class="scroll"><table><thead><tr><th>Entity</th><th>Reason</th><th class=num>Rows</th></tr></thead>
<tbody>{q_rows}</tbody></table></div></section>
</main><div class="tip" role="status"></div><script>{JS}</script></body></html>"""


def main() -> int:
    report = json.loads((REPORTS / "dq_results.json").read_text())
    path = REPORTS / "rule_evaluation.json"
    evaluation = json.loads(path.read_text()) if path.exists() else None
    (REPORTS / "dq_dashboard.html").write_text(render(report, evaluation), encoding="utf-8")
    print(f"Wrote {REPORTS / 'dq_dashboard.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
