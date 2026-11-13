"""Score lit flags against NBER recession starts (USREC)."""
from statistics import median

from pipeline.signals import month_add


def recession_starts(usrec):
    ms = sorted(usrec)
    return [m for i, m in enumerate(ms) if usrec[m] >= 1 and (i == 0 or usrec[ms[i - 1]] < 1)]


def onsets(lit):
    ms = sorted(lit)
    return [m for i, m in enumerate(ms) if lit[m] and (i == 0 or not lit[ms[i - 1]])]


def score(lit, usrec, window):
    """Hit: lit at some month in [start - window, start]. Lead = start - first lit month in that window.
    False positive: an onset not followed by a recession start within `window` months and not inside a recession.
    Only recessions whose window lies inside the signal's history are scored."""
    if not lit:
        return {"hits": 0, "misses": 0, "false_positives": 0, "median_lead_months": None, "leads": [], "scored_recessions": []}
    first, last = min(lit), max(lit)
    starts = [s for s in recession_starts(usrec) if month_add(s, -window) >= first and s <= last]
    hits, misses, leads = 0, 0, []
    for s in starts:
        win = [month_add(s, -k) for k in range(window, -1, -1)]
        lit_months = [m for m in win if lit.get(m)]
        if lit_months:
            hits += 1
            leads.append(_diff(lit_months[0], s))
        else:
            misses += 1
    all_starts = recession_starts(usrec)
    fp = 0
    for o in onsets(lit):
        if usrec.get(o, 0) >= 1:
            continue
        if not any(0 <= _diff(o, s) <= window for s in all_starts):
            # an onset after the data's last recession start may still be "pending": count only if window has elapsed
            if month_add(o, window) <= max(usrec):
                fp += 1
    return {"hits": hits, "misses": misses, "false_positives": fp,
            "median_lead_months": median(leads) if leads else None, "leads": leads, "scored_recessions": starts}


def _diff(a, b):
    """Months from a to b."""
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def run(signals, counts, usrec, cfg):
    w = cfg["backtest"]["window_months"]
    rows = []
    for sid, r in signals.items():
        rows.append({"id": sid, "label": cfg["signals"][sid]["label"], "role": cfg["signals"][sid]["role"], **score(r["lit"], usrec, w)})
    for n in cfg["backtest"]["n_of_prongs"]:
        lit = {m: c >= n for m, c in counts.items()}
        rows.append({"id": f"n_of_prongs_{n}", "label": f"≥{n} prongs lit", "role": "combo", **score(lit, usrec, w)})
    return rows
