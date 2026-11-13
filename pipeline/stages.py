"""Staged view (warning -> arriving -> confirmed) and every past episode of each stage, from config["stages"]."""
from pipeline.backtest import _diff, recession_starts
from pipeline.signals import month_add


def _cond(c, signals, stage_flags, m):
    """True/False, or None if the input has no data for month m."""
    if "stage" in c:
        return stage_flags[c["stage"]].get(m)
    lit = signals[c["signal"]]["lit"]
    if m not in lit:
        return None
    k = c.get("lit_within_months", 0)
    return any(lit.get(month_add(m, -j), False) for j in range(k + 1))


def stage_flags(cfg, signals):
    st = cfg["stages"]
    flags = {}
    months = sorted(set().union(*(set(s["lit"]) for s in signals.values())))
    for sid in st["order"]:
        d = st["definitions"][sid]
        out = {}
        for m in months:
            alls = [_cond(c, signals, flags, m) for c in d.get("all", [])]
            anys = [_cond(c, signals, flags, m) for c in d.get("any", [])]
            if any(v is None for v in alls) or (anys and all(v is None for v in anys)):
                continue
            out[m] = all(alls) and (not anys or any(bool(v) for v in anys))
        flags[sid] = out
    return flags


def episodes(flag, gap):
    """Contiguous lit runs; runs separated by <= gap unlit months are merged."""
    runs = []
    for m in sorted(m for m, v in flag.items() if v):
        if runs and _diff(runs[-1][1], m) <= gap + 1:
            runs[-1][1] = m
        else:
            runs.append([m, m])
    return runs


def outcome(start, usrec, before, after):
    """Match an episode to the recession start nearest to it in [start - before, start + after]."""
    data_end = max(usrec)
    if usrec.get(start, 0) >= 1 and not any(_diff(r, start) <= before and _diff(r, start) >= 0 for r in recession_starts(usrec)):
        return {"result": "during_recession"}
    cands = [r for r in recession_starts(usrec) if -before <= _diff(start, r) <= after]
    if cands:
        r = min(cands, key=lambda r: abs(_diff(start, r)))
        return {"result": "recession", "recession_start": r, "lead_months": _diff(start, r)}
    if month_add(start, after) > data_end:
        return {"result": "open"}
    return {"result": "no_recession"}


def build_stages(cfg, signals, usrec):
    st = cfg["stages"]
    flags = stage_flags(cfg, signals)
    out = {"order": st["order"], "stages": {}}
    for sid in st["order"]:
        d, f = st["definitions"][sid], flags[sid]
        eps, seen = [], set()
        for a, b in episodes(f, st["merge_gap_months"]):
            o = outcome(a, usrec, d["match_before_months"], d["match_after_months"])
            if o.get("recession_start") and o["recession_start"] in seen:
                o = {"result": "repeat", "recession_start": o["recession_start"], "lead_months": o["lead_months"]}
            if o.get("recession_start"):
                seen.add(o["recession_start"])
            eps.append({"start": a, "end": b, "months": _diff(a, b) + 1, "ongoing": b == max(f), **o})
        last = max(f) if f else None
        out["stages"][sid] = {"label": d["label"], "blurb": d["blurb"], "on": bool(last and f[last]), "as_of_month": last,
                              "first_month": min(f) if f else None, "episodes": eps,
                              "summary": {k: sum(e["result"] == k for e in eps) for k in ("recession", "no_recession", "open", "during_recession", "repeat")}}
    on = [s for s in st["order"] if out["stages"][s]["on"]]
    out["current"] = on[-1] if on else None
    return out
