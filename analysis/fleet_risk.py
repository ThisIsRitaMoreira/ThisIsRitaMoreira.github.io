"""
Fleet driver risk (BUAN 6346 Big Data group project) -> data/fleet.js

Reuses the project's own analysis module (ant_advanced_analytics.py) so the
portfolio shows exactly the numbers in the project, then adds two things the
site needs: a gains curve for the event classifier and compact JSON.

Data: the course case files (25 drivers, 20 trucks, 8,000 geolocation pings,
1,350 monthly mileage rows). The case company is fictional; driver names are
left out of the output.

Usage: python fleet_risk.py <ANT_Risk_Factor_Project dir> <analytics dir> <out.js>
"""
import json
import sys
from pathlib import Path

DATA, ANALYTICS, OUT = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(ANALYTICS))
import numpy as np
import pandas as pd
import ant_advanced_analytics as ant
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

t = ant.load(DATA)
_, _, rf = ant.rebuild_pipeline(t)
d = ant.driver_features(t, rf)
bq = ant.business_questions(t, d)
bayes, prior = ant.bayes_forecast(d)
clusters, csum, sil, pc_var = ant.cluster_drivers(d)
metrics, importance, rule, vel = ant.event_classifier(t, d)
EV = list(ant.EVENT_COLORS)
SHORT = {"overspeed": "Overspeed", "lane departure": "Lane departure",
         "unsafe following distance": "Unsafe following", "unsafe tail distance": "Unsafe tail distance"}

# ---------- gains curve: same random-forest setup as the project, cross-validated
g = t["geolocation"].merge(d[["driverid", "cdl_years", "wage_plan", "truck_age", "model"]], on="driverid")
y = g["event_ind"].to_numpy()
num, cat = ["velocity", "idling_ind", "truck_age", "cdl_years"], ["state", "model", "wage_plan"]
pre = ColumnTransformer([("num", StandardScaler(), num), ("cat", OneHotEncoder(handle_unknown="ignore"), cat)])
pipe = Pipeline([("pre", pre), ("clf", RandomForestClassifier(n_estimators=400, min_samples_leaf=5,
                 class_weight="balanced", random_state=ant.SEED, n_jobs=-1))])
pr = cross_val_predict(pipe, g[num + cat], y, cv=StratifiedKFold(5, shuffle=True, random_state=ant.SEED),
                       method="predict_proba")[:, 1]
order = np.argsort(-pr, kind="stable")
caught = np.cumsum(y[order])
gains = [[round(k / len(y), 3), int(caught[k - 1])] for k in
         sorted(set([max(1, int(round(q * len(y)))) for q in np.linspace(0.005, 1, 200)]))]

# ---------- assemble
b = bayes.set_index("driverid")
c = clusters.set_index("driverid")
drivers = []
for _, r in d.sort_values("riskfactor", ascending=False).iterrows():
    i = r.driverid
    drivers.append({
        "id": i, "events": int(r.events), "miles": int(r.totmiles), "rf": round(float(r.riskfactor), 2),
        "alert": bool(r.riskfactor >= ant.THRESHOLD),
        "ev": {SHORT[e]: int(r[e]) for e in EV},
        "wage": r.wage_plan, "cdl": round(float(r.cdl_years), 1), "tenure": str(r.tenure_band),
        "truck": r.truckid, "model": r.model, "truck_age": int(r.truck_age), "mpg": round(float(r.avg_mpg), 2),
        "post": round(float(b.loc[i, "posterior_mean"]), 2), "lo": round(float(b.loc[i, "ci90_low"]), 2),
        "hi": round(float(b.loc[i, "ci90_high"]), 2), "p7": round(float(b.loc[i, "p_true_risk_ge_7"]), 3),
        "exp12": round(float(b.loc[i, "exp_events_next_12m"]), 2), "tier": b.loc[i, "action_tier"],
        "profile": c.loc[i, "profile"], "pc1": round(float(c.loc[i, "pc1"]), 3), "pc2": round(float(c.loc[i, "pc2"]), 3),
    })

same = bq["q2_same_truck"]
shared = [{"truck": tk, "model": x.model.iloc[0], "ratio": round(float(x.risk_ratio.iloc[0]), 1),
           "drivers": [{"id": r.driverid, "rf": round(float(r.riskfactor), 2)} for r in x.itertuples()]}
          for tk, x in same.groupby("truckid")]

ab = g[g.event != "normal"]
by_model = pd.crosstab(ab["model"], ab["event"]).reindex(columns=EV, fill_value=0)
by_model["total"] = by_model.sum(axis=1)
by_model = by_model.sort_values("total", ascending=False)

m = t["truck_mileage"].copy()
m["month"] = pd.to_datetime(m["rdate"] + "-01")
ts = m.groupby("month").agg(miles=("miles", "sum"), mpg=("mpg", "mean")).reset_index()
fc = pd.read_csv(ANALYTICS / "output" / "mileage_mpg_forecast.csv")

city = bq["q3_city"].head(12)
state = bq["q3_state"]
alert_mix = bq["q1_alert_event_mix"]

out = {
    "threshold": ant.THRESHOLD,
    "totals": {"drivers": len(d), "trucks": int(t["trucks"].shape[0]), "pings": int(len(t["geolocation"])),
               "mileage_rows": int(len(m)), "miles": int(m.miles.sum()),
               "events": int(ab.shape[0]), "records": int(len(t["geolocation"]) + len(m) + 25 + 20 + 25)},
    "drivers": drivers,
    "shared": shared,
    "q2": bq["q2_stats"],
    "q4": {**bq["q4_stats"],
           "wage": [{"k": k, "n": int(x.drivers), "avg": round(float(x.avg_risk), 1), "alert": int(x.alert_drivers)}
                    for k, x in bq["q4_wage_plan"].iterrows()],
           "tenure": [{"k": str(k), "n": int(x.drivers), "avg": round(float(x.avg_risk), 1), "alert": int(x.alert_drivers)}
                      for k, x in bq["q4_tenure"].iterrows()]},
    "alert_mix": {SHORT[k]: round(float(v), 3) for k, v in alert_mix.items()},
    "by_model": [{"model": k, **{SHORT[e]: int(x[e]) for e in EV}} for k, x in by_model.iterrows()],
    "events": [SHORT[e] for e in EV],
    "cities": [{"city": x.city, "state": x.state, "pings": int(x.pings), "events": int(x.abnormal),
                "rate": round(float(x.per_1000_pings), 1)} for x in city.itertuples()],
    "states": [{"state": k, "events": int(x.abnormal), "share": round(float(x.share_of_events), 3),
                "rate": round(float(x.per_1000_pings), 1)} for k, x in state.iterrows()],
    "monthly": [{"m": x.month.strftime("%Y-%m"), "miles": int(x.miles), "mpg": round(float(x.mpg), 3)} for x in ts.itertuples()],
    "forecast": [{"m": x.month[:7], "miles": round(x.miles), "lo": round(x.miles_lo), "hi": round(x.miles_hi),
                  "mpg": x.mpg, "mpg_lo": x.mpg_lo, "mpg_hi": x.mpg_hi} for x in fc.itertuples()],
    "prior": prior,
    "clusters": {"silhouette": {str(k): v for k, v in sil.items()}, "pc_var": round(pc_var, 3),
                 "summary": [{"profile": k, **{kk: (round(float(vv), 2) if isinstance(vv, float) else int(vv))
                              for kk, vv in x.items()}} for k, x in csum.iterrows()]},
    "classifier": metrics, "importance": {k: round(float(v), 3) for k, v in importance.items()},
    "velocity_rule": rule, "velocity_by_event": vel, "gains": gains, "base_events": int(y.sum()),
}
print(json.dumps({k: out[k] for k in ["totals", "q2", "classifier", "importance"]}, default=str)[:900])
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("/* generated by analysis/fleet_risk.py: do not edit by hand */\n")
    fh.write("window.DATA_FLEET = " + json.dumps(out, separators=(",", ":"), default=str) + ";\n")
print("wrote", OUT)
