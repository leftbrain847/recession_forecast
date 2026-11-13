import json
import pathlib

import pytest

from pipeline import backtest, build, smoke
from pipeline.fetch import parse_csv, parse_fred_json
from pipeline.signals import compute_signal, forward_fill, moving_avg, persisted, uninverted_after_inversion, yoy_pct

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/signals.json").read_text())


def months(start_year, n):
    return [f"{start_year + i // 12:04d}-{i % 12 + 1:02d}" for i in range(n)]


def test_config_has_required_fields():
    for sid, s in CFG["signals"].items():
        assert sid == sid.lower()
        for k in ("label", "sources", "transform", "persistence_months", "role", "enabled"):
            assert k in s, (sid, k)
        assert s["role"] in ("prong", "watch")
        assert all(src in CFG["sources"] for src in s["sources"])
    banned = {"BAA", "BAA10Y", "DBAA"}
    assert not banned & set(CFG["sources"]), "Moody's series are not redistributable"
    assert not any("ISM" in k or "NAPM" in k for k in CFG["sources"])


def test_ebp_schema_change_fails_loudly():
    good = "date,gz_spread,ebp,est_prob\n2026-10-01,1.0,-0.26,0.11\n"
    assert parse_csv(good, "date", "ebp", ["date", "gz_spread", "ebp", "est_prob"]) == [("2026-10-01", -0.26)]
    with pytest.raises(ValueError, match="schema changed"):
        parse_csv("date,gz,ebp_new\n2026-10-01,1,2\n", "date", "ebp", ["date", "gz_spread", "ebp", "est_prob"])


def test_fred_json_missing_values_and_errors():
    assert parse_fred_json('{"observations":[{"date":"2026-01-01","value":"."},{"date":"2026-02-01","value":"1.5"}]}', "X") == [("2026-02-01", 1.5)]
    with pytest.raises(ValueError):
        parse_fred_json('{"error_code":400,"error_message":"Bad Request. The series does not exist."}', "X")


def test_smoke_reports_empty_stale_and_fetch_errors():
    import datetime as dt
    cfg = {"fred": {"api_key_env": "NO_SUCH_KEY_ENV", "raw_dir_env": "NO_SUCH_DIR_ENV", "min_rows": 2},
           "sources": {"EBP": {"provider": "csv", "url": "x", "date_column": "date", "value_column": "ebp",
                               "expected_columns": ["date", "ebp"], "max_stale_days": 30},
                       "MISSING": {"provider": "fred", "max_stale_days": 30}}}
    report, errors = smoke.run(cfg, get=lambda url, t: "date,ebp\n2020-01-01,1\n2020-02-01,2\n", today=dt.date(2026, 11, 13))
    assert any("EBP" in e and "days old" in e for e in errors)
    assert any(e.startswith("MISSING") for e in errors)
    _, errors = smoke.run(cfg | {"sources": {"EBP": cfg["sources"]["EBP"]}}, get=lambda u, t: "date,ebp\n", today=dt.date(2026, 11, 13))
    assert errors == ["EBP: empty response"]


def test_transforms():
    assert moving_avg({"2020-01": 1, "2020-02": 2, "2020-03": 3, "2020-05": 9}, 3) == {"2020-03": 2}
    assert yoy_pct({"2019-01": 100.0, "2020-01": 80.0}) == {"2020-01": pytest.approx(-20.0)}
    ff = forward_fill({"2020-01": 5, "2020-04": 7}, 3, until="2020-05")
    assert ff == {"2020-01": 5, "2020-02": 5, "2020-03": 5, "2020-04": 7, "2020-05": 7}
    lit, run = persisted({m: True for m in months(2020, 6)} | {"2020-07": False}, 6)
    assert lit["2020-06"] and not lit["2020-05"] and run["2020-07"] == 0


def test_uninverted_after_inversion():
    vals = {"2020-01": -0.2, "2020-02": 0.1}
    assert uninverted_after_inversion(vals, 24) == {"2020-01": False, "2020-02": True}


def test_manufacturing_philly_only_before_cutoff_and_persistence():
    sig = CFG["signals"]["manufacturing"]
    ms = months(2000, 24)
    monthly = {"GACDFSA066MSFRBPHI": {m: -5.0 for m in ms},
               "GACDISA066MSFRBNY": {m: 100.0 for m in ms},   # would flip the average positive if used before 2001
               "BACTSAMFRBDAL": {}}
    r = compute_signal(sig, monthly)
    assert r["values"]["2000-12"] == -5.0
    assert r["lit"]["2000-08"] and not r["lit"]["2000-07"]  # 3-mo MA starts 2000-03, 6 months -> 2000-08
    assert r["values"]["2001-06"] > 0 and not r["lit"]["2001-06"]


def test_credit_any_vs_all():
    sig = json.loads(json.dumps(CFG["signals"]["credit"]))
    monthly = {"EBP": {"2020-01": 0.8, "2020-02": 0.1}, "DRTSCILM": {"2020-01": 10.0}}
    r = compute_signal(sig, monthly)
    assert r["lit"] == {"2020-01": True, "2020-02": False}
    sig["combine"] = "all"
    assert compute_signal(sig, monthly)["lit"]["2020-01"] is False


def test_backtest_hits_misses_false_positives_and_lead():
    ms = months(2000, 60)
    usrec = {m: 0 for m in ms}
    for m in ms[30:36]:
        usrec[m] = 1                       # recession starts 2002-07
    lit = {m: False for m in ms}
    lit["2001-07"] = True                  # 12 months before start -> hit, lead 12
    lit["2004-01"] = True                  # no recession follows within 18 months, window elapsed? data ends 2004-12 -> pending
    lit["2000-01"] = True                  # 30 months before start -> false positive
    s = backtest.score(lit, usrec, 18)
    assert (s["hits"], s["misses"], s["median_lead_months"]) == (1, 0, 12)
    assert s["false_positives"] == 1
    assert backtest.score({m: False for m in ms}, usrec, 18)["misses"] == 1
    only_start = {m: m == "2002-07" for m in ms}
    assert backtest.score(only_start, usrec, 18)["hits"] == 0
    assert backtest.score(only_start, usrec, 18, include_start=True)["hits"] == 1


def test_bad_dates_rejected():
    with pytest.raises(ValueError, match="bad date"):
        parse_csv("date,ebp\n<img src=x>,1\n", "date", "ebp")


def test_build_end_to_end_from_fixtures(monkeypatch):
    monkeypatch.setenv("RF_RAW_DIR", str(ROOT / "tests/fixtures"))
    from pipeline.fetch import fetch_all
    data = build.build(CFG, fetch_all(CFG))
    assert set(data["prongs"]) == {"yield_curve", "unemployment", "manufacturing", "credit"}
    assert data["signals"]["housing"]["role"] == "watch"
    assert {r["id"] for r in data["backtest"]} >= {"yield_curve", "n_of_prongs_2"}
    assert data["sources"]["EBP"]["last_observation"]
    for c in data["signals"].values():
        assert {"lit", "value", "months_persisted", "series"} <= set(c)


def _sig(lit):
    return {"lit": lit}


def test_stage_flags_warning_lookback_and_arriving_needs_warning():
    from pipeline.stages import stage_flags
    ms = months(2000, 40)
    yc = {m: m == "2000-06" for m in ms}                 # one inverted month
    man = {m: m in ("2002-05", "2002-07") for m in ms}  # inside then outside the 24-mo window
    sigs = {"yield_curve": _sig(yc), "manufacturing": _sig(man), "credit": _sig({m: False for m in ms}),
            "unemployment": _sig({m: False for m in ms})}
    f = stage_flags(CFG, sigs)
    assert f["warning"]["2002-06"] and not f["warning"]["2002-07"]
    assert f["arriving"]["2002-05"] and not f["arriving"]["2002-07"]


def test_episodes_merge_gap_and_outcomes():
    from pipeline.stages import episodes, outcome
    flag = {m: m in ("2000-01", "2000-02", "2000-05", "2001-01") for m in months(2000, 24)}
    assert episodes(flag, 3) == [["2000-01", "2000-05"], ["2001-01", "2001-01"]]
    usrec = {m: int("2001-06" <= m <= "2001-11") for m in months(1999, 120)}
    assert outcome("2000-01", usrec, 0, 18) == {"result": "recession", "recession_start": "2001-06", "lead_months": 17}
    assert outcome("2001-09", usrec, 12, 12)["lead_months"] == -3
    assert outcome("2004-01", usrec, 0, 18) == {"result": "no_recession"}
    assert outcome("2008-01", usrec, 0, 18) == {"result": "open"}


def test_build_includes_stage_history(monkeypatch):
    monkeypatch.setenv("RF_RAW_DIR", str(ROOT / "tests/fixtures"))
    from pipeline.fetch import fetch_all
    st = build.build(CFG, fetch_all(CFG))["stages"]
    assert st["order"] == ["warning", "arriving", "confirmed"]
    w = st["stages"]["warning"]["episodes"]
    assert any(e["result"] == "recession" and e["recession_start"] == "2008-01" for e in w)
