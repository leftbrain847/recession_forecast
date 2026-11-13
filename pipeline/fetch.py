"""Fetch raw series. FRED via its official API (FRED_API_KEY). Set RF_RAW_DIR to read saved CSVs instead
(offline fixtures / local cache): <dir>/<SERIES>.csv in FRED download format, <dir>/EBP.csv as published."""
import csv
import io
import json
import os
import re
import urllib.parse
import urllib.request


def http_get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "recession_forecast/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} for {url.split('?')[0]}")  # never echo the api_key query
        return r.read().decode("utf-8-sig")


def parse_value(v):
    v = (v or "").strip()
    if v in ("", "."):
        return None
    return float(v)


DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_date(d):
    if not DATE.match(d):
        raise ValueError(f"bad date {d!r}")
    return d


def parse_csv(text, date_col, value_col, expected_columns=None):
    reader = csv.DictReader(io.StringIO(text))
    cols = reader.fieldnames or []
    if expected_columns and list(cols) != list(expected_columns):
        raise ValueError(f"schema changed: expected columns {expected_columns}, got {cols}")
    if date_col not in cols or value_col not in cols:
        raise ValueError(f"missing column {date_col!r} or {value_col!r}; got {cols}")
    out = []
    for row in reader:
        val = parse_value(row[value_col])
        if val is not None:
            out.append((check_date(row[date_col][:10]), val))
    return out


def parse_fred_json(text, series_id):
    data = json.loads(text)
    if "observations" not in data:
        raise ValueError(f"{series_id}: FRED response has no 'observations' (keys: {list(data)})")
    out = []
    for o in data["observations"]:
        val = parse_value(o.get("value"))
        if val is not None:
            out.append((check_date(o["date"]), val))
    return out


def fetch_source(sid, src, fred_cfg, get=http_get):
    timeout = fred_cfg.get("timeout_seconds", 60)
    raw_dir = os.environ.get(fred_cfg.get("raw_dir_env", "RF_RAW_DIR"))
    if raw_dir:
        text = open(os.path.join(raw_dir, f"{sid}.csv"), encoding="utf-8-sig").read()
        if src["provider"] == "csv":
            return parse_csv(text, src["date_column"], src["value_column"], src.get("expected_columns"))
        rows = parse_csv(text, "observation_date", sid)
        return [r for r in rows if r[0] >= src.get("start", "")]
    if src["provider"] == "csv":
        text = get(src["url"], timeout)
        return parse_csv(text, src["date_column"], src["value_column"], src.get("expected_columns"))
    key = os.environ.get(fred_cfg["api_key_env"])
    if not key:
        raise RuntimeError(f"{fred_cfg['api_key_env']} is not set (or set RF_RAW_DIR for offline CSVs)")
    q = {"series_id": sid, "api_key": key, "file_type": "json"}
    if src.get("start"):
        q["observation_start"] = src["start"]
    return parse_fred_json(get(fred_cfg["api_url"] + "?" + urllib.parse.urlencode(q), timeout), sid)


def fetch_all(cfg, get=http_get):
    return {sid: fetch_source(sid, src, cfg["fred"], get) for sid, src in cfg["sources"].items()}
