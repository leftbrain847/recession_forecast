"""Fetch -> signals -> backtest -> docs/data/signals.json."""
import datetime as dt
import json
import os
import sys

from pipeline import backtest
from pipeline.fetch import fetch_all
from pipeline.signals import compute_all, prongs_lit
from pipeline.stages import build_stages


def r2(v):
    return None if v is None else round(v, 3)


def build(cfg, raw, now=None):
    signals, monthly = compute_all(cfg, raw)
    counts, prong_ids = prongs_lit(signals, cfg)
    usrec = monthly[cfg["backtest"]["recession_source"]]
    start = cfg["output"]["chart_start"]
    out_signals = {}
    for sid, r in signals.items():
        sc = cfg["signals"][sid]
        last = max(r["lit"])
        card = {
            "id": sid, "label": sc["label"], "role": sc["role"], "units": sc.get("units", ""),
            "short_label": sc.get("short_label", sc["label"]), "plain": sc.get("plain", ""), "trigger_text": sc.get("trigger_text", ""),
            "threshold": sc.get("threshold"), "components_cfg": sc.get("components"), "combine": sc.get("combine"),
            "persistence_months": sc["persistence_months"],
            "as_of_month": last, "lit": r["lit"][last], "value": r2(r["values"].get(last)),
            "months_persisted": r["run"][last],
            "series": [[m, r2(v)] for m, v in r["values"].items() if m >= start],
        }
        if r.get("components"):
            card["component_values"] = {s: {"month": max(v), "value": r2(v[max(v)])} for s, v in r["components"].items()}
        if "uninverted" in r:
            card["uninverted_after_inversion"] = r["uninverted"][last]
        out_signals[sid] = card
    last_count_month = max(counts)
    return {
        "generated_at": (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds"),
        "prongs": prong_ids,
        "prongs_lit": {"month": last_count_month, "count": counts[last_count_month], "of": len(prong_ids)},
        "prongs_lit_now": sum(out_signals[p]["lit"] for p in prong_ids),
        "signals": out_signals,
        "recessions": [[m, int(v)] for m, v in usrec.items() if m >= start],
        "recessions_all": [[m, int(v)] for m, v in usrec.items() if m >= cfg["output"].get("timeline_start", start)],
        "backtest": backtest.run(signals, counts, usrec, cfg),
        "stages": build_stages(cfg, signals, usrec) if "stages" in cfg else None,
        "backtest_window_months": cfg["backtest"]["window_months"],
        "sources": {sid: {"last_observation": raw[sid][-1][0], "first_observation": raw[sid][0][0],
                          "attribution": cfg["sources"][sid]["attribution"]} for sid in raw},
    }


def main(config_path="config/signals.json"):
    cfg = json.load(open(config_path))
    data = build(cfg, fetch_all(cfg))
    path = cfg["output"]["path"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"wrote {path}: {data['prongs_lit_now']}/{len(data['prongs'])} prongs lit", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:])
