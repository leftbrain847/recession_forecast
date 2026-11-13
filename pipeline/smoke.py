"""STEP 0: fetch every source, fail loudly on missing series, empty response, schema change or stale data."""
import datetime as dt
import json
import sys

from pipeline.fetch import fetch_source, http_get


def check_rows(sid, src, rows, min_rows, today):
    errs = []
    if not rows:
        return [f"{sid}: empty response"]
    if len(rows) < min_rows:
        errs.append(f"{sid}: only {len(rows)} rows (< {min_rows})")
    last = dt.date.fromisoformat(rows[-1][0])
    age = (today - last).days
    if age > src["max_stale_days"]:
        errs.append(f"{sid}: last observation {last} is {age} days old (> {src['max_stale_days']})")
    return errs


def run(cfg, get=http_get, today=None):
    today = today or dt.date.today()
    errors, report = [], {}
    for sid, src in cfg["sources"].items():
        try:
            rows = fetch_source(sid, src, cfg["fred"], get)
        except Exception as e:  # noqa: BLE001 - report every failure, then fail
            errors.append(f"{sid}: {type(e).__name__}: {e}")
            continue
        errors += check_rows(sid, src, rows, cfg["fred"]["min_rows"], today)
        if rows:
            report[sid] = {"rows": len(rows), "first": rows[0][0], "last": rows[-1][0]}
    return report, errors


def main():
    cfg = json.load(open("config/signals.json"))
    report, errors = run(cfg)
    for sid, r in report.items():
        print(f"ok  {sid:20s} {r['rows']:6d} rows {r['first']} .. {r['last']}")
    for e in errors:
        print(f"FAIL {e}", file=sys.stderr)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
