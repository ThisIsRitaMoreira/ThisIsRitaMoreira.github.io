"""
People Services SLA, backlog and repeat-ticket analysis.

Source  : UCI ML Repository #498, "Incident management process enriched event log"
          (ServiceNow audit log from an IT service desk, CC BY 4.0).
          https://archive.ics.uci.edu/dataset/498
Stand-in: the log is an IT desk, not HR, but the mechanics are the same ones I
          tracked at ALTEN People Services: SLA timers, reassignment, reopen,
          repeat contacts from the same requester.

Usage   : python people_services.py <path/to/incident_event_log.csv> <out.js>
Output  : a JS file that sets window.DATA_PEOPLE (so the site works offline).
"""
import json
import sys

import numpy as np
import pandas as pd

SRC, OUT = sys.argv[1], sys.argv[2]
REPEAT_WINDOW_DAYS = 14
START, END = "2016-03-01", "2016-06-01"   # the dense part of the log (3 full months)

# ---------------------------------------------------------------- load + collapse
# The file is an event log: one row per update. Keep the final state per ticket.
ev = pd.read_csv(SRC, na_values="?", low_memory=False)
t = ev.sort_values("sys_mod_count").groupby("number").tail(1).copy()
for c in ["opened_at", "resolved_at", "closed_at"]:
    t[c] = pd.to_datetime(t[c], format="%d/%m/%Y %H:%M", errors="coerce")
t = t[(t.opened_at >= START) & (t.opened_at < END)].sort_values("opened_at")
t["done_at"] = t.resolved_at.fillna(t.closed_at)
t["res_h"] = (t.done_at - t.opened_at).dt.total_seconds() / 3600

# A "repeat ticket": the same requester comes back about the same category within
# 14 days, or the requester rejected the resolution (reopen_count > 0).
prev = t.groupby(["caller_id", "category"]).opened_at.shift(1)
t["repeat"] = ((t.opened_at - prev).dt.days < REPEAT_WINDOW_DAYS) | (t.reopen_count > 0)
t["made_sla"] = t.made_sla.astype(bool)
t["knowledge"] = t.knowledge.astype(bool)
t["prio"] = t.priority.str.split(" - ").str[1]

teams = ["All teams"] + t.assignment_group.value_counts().head(5).index.tolist()


def r(x, n=4):
    return None if pd.isna(x) else round(float(x), n)


def team_block(d):
    days = pd.date_range(START, pd.Timestamp(END) - pd.Timedelta(days=1), freq="D")
    end_of_day = days + pd.Timedelta(days=1)
    o = d.opened_at.values
    f = d.done_at.fillna(pd.Timestamp("2099-01-01")).values
    backlog, aging = [], []
    for e in end_of_day:
        open_mask = (o < e.to_datetime64()) & (f >= e.to_datetime64())
        backlog.append(int(open_mask.sum()))
        age = (e.to_datetime64() - o[open_mask]) / np.timedelta64(1, "D")
        aging.append([int((age <= 2).sum()), int(((age > 2) & (age <= 7)).sum()),
                      int(((age > 7) & (age <= 30)).sum()), int((age > 30).sum())])
    opened = d.groupby(d.opened_at.dt.normalize()).size().reindex(days, fill_value=0)
    resolved = d.groupby(d.done_at.dt.normalize()).size().reindex(days, fill_value=0)

    wk = d.assign(w=d.opened_at.dt.to_period("W-SUN").dt.start_time)
    weekly = wk.groupby("w").agg(n=("number", "size"), sla=("made_sla", "mean"),
                                 rep=("repeat", "mean"), mres=("res_h", "median"))
    prio = d.groupby("prio").agg(n=("number", "size"), sla=("made_sla", "mean"),
                                 mres=("res_h", "median"))
    prio = prio.reindex(["Critical", "High", "Moderate", "Low"]).dropna(how="all")
    ra = d.assign(b=d.reassignment_count.clip(upper=4)).groupby("b").agg(
        n=("number", "size"), sla=("made_sla", "mean"), mres=("res_h", "median"))

    # Repeat-ticket drivers by category, split by whether a knowledge article was used.
    g = d.groupby("category")
    cat = pd.DataFrame({
        "n": g.size(), "rep": g.repeat.sum(), "sla": g.made_sla.mean(),
        "n_nokb": g.apply(lambda x: (~x.knowledge).sum(), include_groups=False),
        "rep_nokb": g.apply(lambda x: x.loc[~x.knowledge, "repeat"].sum(), include_groups=False),
        "n_kb": g.knowledge.sum(),
        "rep_kb": g.apply(lambda x: x.loc[x.knowledge, "repeat"].sum(), include_groups=False),
    }).sort_values("rep", ascending=False)
    top = cat.head(12)
    other = cat.iloc[12:].sum(numeric_only=True)

    months = d.opened_at.dt.to_period("M").nunique()
    return {
        "kpi": {
            "tickets": int(len(d)), "per_month": round(len(d) / months),
            "sla": r(d.made_sla.mean()), "repeat": r(d.repeat.mean()),
            "median_res_h": r(d.res_h.median(), 1),
            "reassigned": r((d.reassignment_count > 0).mean()),
            "kb_rate": r(d.knowledge.mean()),
            "rep_kb": r(d.loc[d.knowledge, "repeat"].mean()),
            "rep_nokb": r(d.loc[~d.knowledge, "repeat"].mean()),
        },
        "days": [x.strftime("%Y-%m-%d") for x in days],
        "opened": opened.astype(int).tolist(),
        "resolved": resolved.astype(int).tolist(),
        "backlog": backlog,
        "aging": aging,
        "weekly": [{"w": i.strftime("%Y-%m-%d"), "n": int(x.n), "sla": r(x.sla),
                    "rep": r(x.rep), "mres": r(x.mres, 1)} for i, x in weekly.iterrows()],
        "priority": [{"p": i, "n": int(x.n), "sla": r(x.sla), "mres": r(x.mres, 1)}
                     for i, x in prio.iterrows()],
        "reassign": [{"b": int(i), "n": int(x.n), "sla": r(x.sla), "mres": r(x.mres, 1)}
                     for i, x in ra.iterrows()],
        "categories": [{"c": i.replace("Category ", "Cat. "), **{k: (r(v) if k == "sla" else int(v))
                        for k, v in x.items()}} for i, x in top.iterrows()],
        "other": {k: int(other[k]) for k in ["n", "rep", "n_nokb", "rep_nokb", "n_kb", "rep_kb"]},
    }


out = {
    "source": {"name": "UCI #498 · ServiceNow incident event log", "license": "CC BY 4.0",
               "url": "https://archive.ics.uci.edu/dataset/498",
               "events": int(len(ev)), "tickets_total": int(ev.number.nunique()),
               "window": f"{START} to 2016-05-31", "repeat_window_days": REPEAT_WINDOW_DAYS},
    "teams": teams,
    "data": {},
}
for name in teams:
    d = t if name == "All teams" else t[t.assignment_group == name]
    out["data"][name] = team_block(d)
    print(name, out["data"][name]["kpi"])

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("/* generated by analysis/people_services.py — do not edit by hand */\n")
    fh.write("window.DATA_PEOPLE = " + json.dumps(out, separators=(",", ":")) + ";\n")
print("wrote", OUT)
