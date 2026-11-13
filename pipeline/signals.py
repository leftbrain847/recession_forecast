"""Turn raw series into monthly signal values and lit flags, driven entirely by config/signals.json."""
import operator

OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq}


def ym(date):
    return date[:7]


def month_add(m, k):
    y, mo = int(m[:4]), int(m[5:7])
    n = y * 12 + (mo - 1) + k
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def month_range(a, b):
    out, m = [], a
    while m <= b:
        out.append(m)
        m = month_add(m, 1)
    return out


def to_monthly(rows):
    """Average observations within each calendar month -> {YYYY-MM: value}."""
    acc = {}
    for d, v in rows:
        acc.setdefault(ym(d), []).append(v)
    return {m: sum(vs) / len(vs) for m, vs in sorted(acc.items())}


def forward_fill(series, months, until=None):
    """Carry each value forward up to `months` - 1 extra months (quarterly -> monthly), never past `until`."""
    out = dict(series)
    for m, v in sorted(series.items()):
        for k in range(1, months):
            nm = month_add(m, k)
            if nm in series or (until and nm > until):
                break
            out.setdefault(nm, v)
    return dict(sorted(out.items()))


def moving_avg(series, n):
    keys = sorted(series)
    out = {}
    for i in range(n - 1, len(keys)):
        win = keys[i - n + 1: i + 1]
        if win[-1] == month_add(win[0], n - 1):  # contiguous months only
            out[keys[i]] = sum(series[k] for k in win) / n
    return out


def yoy_pct(series):
    return {m: (v / series[month_add(m, -12)] - 1) * 100
            for m, v in series.items() if series.get(month_add(m, -12))}


def persisted(cond, need):
    """cond: {month: bool}. Returns ({month: lit}, {month: consecutive months true})."""
    lit, run, streak, prev = {}, {}, 0, None
    for m in sorted(cond):
        streak = streak + 1 if cond[m] and (prev is None or m == month_add(prev, 1)) else (1 if cond[m] else 0)
        prev = m
        run[m] = streak
        lit[m] = streak >= need
    return lit, run


def compute_signal(sig, monthly):
    t = sig["transform"]
    comps = None
    if t in ("monthly_mean", "level"):
        values = monthly[sig["sources"][0]]
    elif t == "yoy_pct":
        values = yoy_pct(monthly[sig["sources"][0]])
    elif t == "mean_available_then_ma":
        first = sig["sources"][0]
        cutoff = sig.get("philly_only_before", "")
        months = sorted(set().union(*(monthly[s] for s in sig["sources"])))
        avg = {}
        for m in months:
            use = [first] if m < cutoff else sig["sources"]
            vals = [monthly[s][m] for s in use if m in monthly[s]]
            if vals:
                avg[m] = sum(vals) / len(vals)
        values = moving_avg(avg, sig["ma_months"])
    elif t == "components":
        comps = {}
        latest = max(max(monthly[c["source"]]) for c in sig["components"])
        for c in sig["components"]:
            s = monthly[c["source"]]
            if c.get("forward_fill_months"):
                s = forward_fill(s, c["forward_fill_months"], until=latest)
            comps[c["source"]] = s
        months = sorted(set().union(*comps.values()))
        start = min(min(s) for s in comps.values())
        values, cond = {}, {}
        for m in months:
            if m < start:
                continue
            hits = [OPS[c["op"]](comps[c["source"]][m], c["value"]) for c in sig["components"] if m in comps[c["source"]]]
            if not hits:
                continue
            ok = any(hits) if sig.get("combine", "any") == "any" else (len(hits) == len(sig["components"]) and all(hits))
            cond[m] = ok
            values[m] = comps[sig["components"][0]["source"]].get(m)
        lit, run = persisted(cond, sig["persistence_months"])
        return {"values": values, "lit": lit, "run": run, "components": comps}
    else:
        raise ValueError(f"unknown transform {t!r}")
    th = sig["threshold"]
    cond = {m: OPS[th["op"]](v, th["value"]) for m, v in values.items()}
    lit, run = persisted(cond, sig["persistence_months"])
    return {"values": values, "lit": lit, "run": run, "components": comps}


def uninverted_after_inversion(values, lookback):
    out = {}
    for m, v in values.items():
        past = [values.get(month_add(m, -k)) for k in range(1, lookback + 1)]
        out[m] = v >= 0 and any(p is not None and p < 0 for p in past)
    return out


def compute_all(cfg, raw):
    monthly = {sid: to_monthly(rows) for sid, rows in raw.items()}
    out = {}
    for sid, sig in cfg["signals"].items():
        if not sig.get("enabled", True):
            continue
        r = compute_signal(sig, monthly)
        if "uninverted_lookback_months" in sig:
            r["uninverted"] = uninverted_after_inversion(r["values"], sig["uninverted_lookback_months"])
        out[sid] = r
    return out, monthly


def prongs_lit(signals, cfg):
    """{month: count lit} over months where every enabled prong has data."""
    ids = [s for s, c in cfg["signals"].items() if c.get("enabled", True) and c["role"] == "prong" and s in signals]
    months = set.intersection(*(set(signals[s]["lit"]) for s in ids)) if ids else set()
    return {m: sum(signals[s]["lit"][m] for s in ids) for m in sorted(months)}, ids
