"""
Alaska (AS) + Hawaiian (HA), 2024: testing the BUAN 6335 platform ideas on a real merger
-> data/airline_real.js

The course project designed a lakehouse for a fictional merger (SkyRoam + Merit): a canonical
"flight leg" keyed on operating carrier + flight number + scheduled departure date (UTC) + origin,
an on-time standard "A14" (arrival within 14 minutes) and a real-time "Live Flight State" for the
operations control center. This script applies those ideas to Alaska + Hawaiian (merger closed
2024-09-18) using public BTS data.

Data
  * BTS Reporting Carrier On-Time Performance, 2024 monthly zips (public domain).
    Only the two reporting carriers AS and HA are kept. BTS covers each carrier's own domestic
    scheduled flights: regional partners (Horizon, SkyWest) and international flights are not in it.
  * OurAirports airports.csv (public domain) for coordinates.

Steps
  1. extract  - read every zip in <bts_zip_dir>, keep AS/HA rows and the columns used below,
                cache them as <filtered.csv.gz> (re-used on later runs; delete it to rebuild).
  2. times    - BTS clock times are local hhmm at each airport. Each airport gets an IANA time
                zone (state default + overrides for split states); local -> UTC with the real 2024
                DST rules. Arrival day is fixed with the scheduled elapsed time. The conversion is
                checked: sched arr - sched dep must equal CRSElapsedTime for every flight.
  3. A network & overlap, B operations, C worst day + replay, D delay propagation,
     E canonical flight-leg examples.
  4. write compact JSON to <out.js> as window.DATA_AIRLINE_REAL.

Usage
  python -I analysis/airline_bts.py <bts_zip_dir> <ourairports airports.csv> <filtered.csv.gz> <out.js>
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ZIP_DIR, AIRPORTS_CSV, FILTERED, OUT = (Path(a) for a in sys.argv[1:5])
CARRIERS = ["AS", "HA"]
NAMES = {"AS": "Alaska Airlines", "HA": "Hawaiian Airlines"}
MERGER_CLOSE = "2024-09-18"
EPOCH = pd.Timestamp("2024-01-01", tz="UTC")       # all instants are kept as minutes since this

KEEP = ["FlightDate", "Reporting_Airline", "Tail_Number", "Flight_Number_Reporting_Airline",
        "Origin", "OriginCityName", "OriginState", "Dest", "DestCityName", "DestState",
        "CRSDepTime", "DepTime", "DepDelay", "DepDel15", "TaxiOut", "WheelsOff", "WheelsOn", "TaxiIn",
        "CRSArrTime", "ArrTime", "ArrDelay", "ArrDel15", "Cancelled", "CancellationCode", "Diverted",
        "CRSElapsedTime", "ActualElapsedTime", "AirTime", "Distance",
        "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
        "DivAirportLandings", "DivReachedDest", "DivArrDelay", "Div1Airport"]
NUM = ["DepDelay", "DepDel15", "TaxiOut", "TaxiIn", "ArrDelay", "ArrDel15", "Cancelled", "Diverted",
       "CRSElapsedTime", "ActualElapsedTime", "AirTime", "Distance", "CarrierDelay", "WeatherDelay",
       "NASDelay", "SecurityDelay", "LateAircraftDelay", "DivAirportLandings", "DivReachedDest",
       "DivArrDelay"]
CAUSES = {"carrier": "CarrierDelay", "weather": "WeatherDelay", "nas": "NASDelay",
          "security": "SecurityDelay", "late_aircraft": "LateAircraftDelay"}
CANCEL_CODES = {"A": "Carrier", "B": "Weather", "C": "National Air System", "D": "Security"}


# ---------------------------------------------------------------- 1. extract
def extract():
    """Filter the monthly zips to AS/HA; cache as gzip CSV (raw BTS text values)."""
    if FILTERED.exists():
        print(f"using cached {FILTERED}")
        return pd.read_csv(FILTERED, dtype=str)
    parts, report = [], []
    for zp in sorted(ZIP_DIR.glob("*.zip")):
        try:
            with zipfile.ZipFile(zp) as z:
                member = next(n for n in z.namelist() if n.lower().endswith(".csv"))
                with z.open(member) as f:
                    rows = 0
                    for chunk in pd.read_csv(f, usecols=KEEP, dtype=str, chunksize=250_000):
                        rows += len(chunk)
                        parts.append(chunk[chunk["Reporting_Airline"].isin(CARRIERS)])
            report.append((zp.name, rows))
            print(f"  {zp.name}: {rows:,} rows read")
        except Exception as e:                                  # partial download, bad zip ...
            print(f"  SKIPPED {zp.name}: {e}")
    df = pd.concat(parts, ignore_index=True)[KEEP]
    FILTERED.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(FILTERED, index=False, compression="gzip")
    print(f"cached {len(df):,} AS/HA rows -> {FILTERED}")
    return df


# ---------------------------------------------------------------- 2. time zones and UTC
LA, DEN, CHI, NY = "America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York"
STATE_TZ = {
    "AK": "America/Anchorage", "HI": "Pacific/Honolulu", "WA": LA, "OR": LA, "CA": LA, "NV": LA,
    "ID": "America/Boise", "AZ": "America/Phoenix", "UT": DEN, "CO": DEN, "NM": DEN, "WY": DEN,
    "MT": DEN, "TX": CHI, "OK": CHI, "KS": CHI, "NE": CHI, "SD": CHI, "ND": CHI, "MN": CHI, "IA": CHI,
    "MO": CHI, "AR": CHI, "LA": CHI, "MS": CHI, "AL": CHI, "WI": CHI, "IL": CHI, "TN": CHI,
    "IN": "America/Indiana/Indianapolis", "MI": "America/Detroit", "KY": NY, "OH": NY, "GA": NY,
    "FL": NY, "SC": NY, "NC": NY, "VA": NY, "WV": NY, "MD": NY, "DE": NY, "PA": NY, "NJ": NY, "NY": NY,
    "CT": NY, "RI": NY, "MA": NY, "VT": NY, "NH": NY, "ME": NY, "DC": NY,
    "PR": "America/Puerto_Rico", "VI": "America/St_Thomas", "TT": "Pacific/Guam"}
# airports in states that span two zones (only matters if served; the elapsed-time check catches misses)
AIRPORT_TZ = {"ADK": "America/Adak", "ELP": DEN, "PNS": CHI, "VPS": CHI, "ECP": CHI, "LWS": LA,
              "TYS": NY, "TRI": NY, "CHA": NY, "RAP": DEN, "DIK": DEN, "ISN": CHI, "PPG": "Pacific/Pago_Pago",
              "SPN": "Pacific/Saipan", "GUM": "Pacific/Guam", "IMT": CHI, "EKO": LA}


def hhmm(s):
    """'hhmm' text -> minutes after local midnight (2400 -> 1440), NaN when blank."""
    v = pd.to_numeric(s, errors="coerce")
    return (v // 100) * 60 + v % 100


def to_utc_min(naive_min, zones):
    """naive local instants (minutes since 2024-01-01 00:00 local) + IANA zone per row
    -> minutes since 2024-01-01 00:00 UTC. DST gaps shift forward; repeated hour takes DST."""
    out = pd.Series(np.nan, index=naive_min.index)
    base = pd.Timestamp("2024-01-01")
    for z, idx in zones.groupby(zones).groups.items():
        ts = base + pd.to_timedelta(naive_min.loc[idx], unit="min")
        loc = ts.dt.tz_localize(z, ambiguous=np.ones(len(ts), bool), nonexistent="shift_forward")
        out.loc[idx] = (loc.dt.tz_convert("UTC") - EPOCH) / pd.Timedelta(minutes=1)
    return out


def prepare(raw):
    df = raw.copy()
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["fn"] = pd.to_numeric(df["Flight_Number_Reporting_Airline"]).astype(int)
    df["date"] = pd.to_datetime(df["FlightDate"])
    df["day0"] = ((df["date"] - pd.Timestamp("2024-01-01")).dt.days * 1440).astype(int)
    for c in ["CRSDepTime", "DepTime", "CRSArrTime", "ArrTime", "WheelsOff", "WheelsOn"]:
        df[c + "_m"] = hhmm(df[c])
    df["o_tz"] = df["Origin"].map(AIRPORT_TZ).fillna(df["OriginState"].map(STATE_TZ))
    df["d_tz"] = df["Dest"].map(AIRPORT_TZ).fillna(df["DestState"].map(STATE_TZ))
    assert df["o_tz"].notna().all() and df["d_tz"].notna().all(), "airport without a time zone"

    # scheduled departure: local date = FlightDate, local clock = CRSDepTime at the origin
    df["sdep"] = to_utc_min(df["day0"] + df["CRSDepTime_m"], df["o_tz"])
    # scheduled arrival: CRSArrTime is local at the destination, possibly the next calendar day.
    guess = to_utc_min(df["day0"] + df["CRSArrTime_m"], df["d_tz"])
    want = df["sdep"] + df["CRSElapsedTime"].fillna(0)
    df["arr_k"] = np.round((want - guess) / 1440).astype(int)       # whole days to add (0 or 1)
    df["sarr"] = to_utc_min(df["day0"] + 1440 * df["arr_k"] + df["CRSArrTime_m"], df["d_tz"])
    df["tz_resid"] = df["sarr"] - df["sdep"] - df["CRSElapsedTime"]  # 0 if both zones are right

    # actual times = scheduled + reported delay (BTS delays are signed minutes vs schedule)
    df["adep"] = df["sdep"] + df["DepDelay"]
    arr_delay = df["ArrDelay"].where(df["Diverted"] == 0,
                                     df["DivArrDelay"].where(df["DivReachedDest"] == 1))
    df["aarr"] = df["sarr"] + arr_delay
    df["woff"] = df["adep"] + df["TaxiOut"]
    df["won"] = (df["aarr"] - df["TaxiIn"]).where(df["Diverted"] == 0)
    # check: local clock of the computed actual departure must equal DepTime
    dep_ok = ((df["CRSDepTime_m"] + df["DepDelay"]) % 1440 == df["DepTime_m"] % 1440)
    df["dep_clock_ok"] = dep_ok.where(df["DepDelay"].notna() & df["DepTime_m"].notna())
    # BTS sometimes reports a gate departure (218 flights) or even a wheels-off (78) before a
    # cancellation. For the replay a cancelled flight never departs: its actual times are dropped.
    cx = df["Cancelled"] == 1
    df.loc[cx, ["adep", "aarr", "woff", "won"]] = np.nan
    # end of the airborne interval: wheels-on, else gate arrival (diverted flights that reached the
    # destination); NaN for diverted flights that never reached it (left out of airborne counts)
    df["air_end"] = df["won"].fillna(df["aarr"])

    df["arrived"] = (df["Cancelled"] == 0) & (df["Diverted"] == 0) & df["ArrDelay"].notna()
    df["mkt"] = np.where(df["Origin"] < df["Dest"], df["Origin"] + "-" + df["Dest"],
                         df["Dest"] + "-" + df["Origin"])
    df["touch_hi"] = (df["OriginState"] == "HI") | (df["DestState"] == "HI")
    df["touch_ak"] = (df["OriginState"] == "AK") | (df["DestState"] == "AK")
    return df


# ---------------------------------------------------------------- helpers
def r(x, n=4):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), n)


def num(v):
    """numpy/pandas scalar -> plain int / float / None for JSON."""
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, (float, np.floating)):
        if np.isnan(v):
            return None
        return int(v) if float(v).is_integer() else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    return v


def table(df, cols):
    return {"cols": cols, "rows": [[num(v) for v in row] for row in df[cols].itertuples(index=False)]}


def ops_stats(g):
    """Operational KPIs for any slice of flights (one carrier, a month, a day...)."""
    arr = g[g["arrived"]]
    dep = g[g["Cancelled"] == 0]
    n = len(g)
    cause_min = {k: float(g[c].fillna(0).sum()) for k, c in CAUSES.items()}
    tot = sum(cause_min.values())
    return {
        "flights": n,                                   # scheduled flights reported to BTS
        "completed": int((g["Cancelled"] == 0).sum()),  # not cancelled (includes diverted)
        "cancelled": int(g["Cancelled"].sum()),
        "diverted": int(g["Diverted"].sum()),
        "arrived": len(arr),                            # completed and not diverted
        "cancel_rate": r(g["Cancelled"].mean()),
        "divert_rate": r(g["Diverted"].mean()),
        "otp": {"A0": r((arr["ArrDelay"] <= 0).mean()),
                "A14": r((arr["ArrDel15"] == 0).mean()),
                "A30": r((arr["ArrDelay"] <= 30).mean())},
        "a14_of_scheduled": r((g["arrived"] & (g["ArrDel15"] == 0)).sum() / n) if n else None,
        "dep": {"D0": r((dep["DepDelay"] <= 0).mean()), "D14": r((dep["DepDel15"] == 0).mean())},
        "avg_arr_delay": r(arr["ArrDelay"].mean(), 1),
        "median_arr_delay": r(arr["ArrDelay"].median(), 1),
        "cause_minutes": {k: int(v) for k, v in cause_min.items()},
        "cause_share": {k: r(v / tot) if tot else None for k, v in cause_min.items()},
    }


# ---------------------------------------------------------------- main
raw = extract()
df = prepare(raw)
months = sorted(df["date"].dt.month.unique().tolist())
print(f"{len(df):,} flights, months {months}")

tz_check = {
    "flights_checked": int(df["tz_resid"].notna().sum()),
    "elapsed_mismatch": int((df["tz_resid"].abs() > 0).sum()),
    "mismatch_by_airport_pair": df.loc[df["tz_resid"].abs() > 0, "mkt"].value_counts().head(10).to_dict(),
    "dep_clock_checked": int(df["dep_clock_ok"].notna().sum()),
    "dep_clock_mismatch": int((df["dep_clock_ok"] == False).sum()),  # noqa: E712
}
print("time-zone check:", tz_check)

# airports (OurAirports) -------------------------------------------------------------
ap = pd.read_csv(AIRPORTS_CSV, usecols=["iata_code", "name", "latitude_deg", "longitude_deg",
                                        "iso_country", "type", "scheduled_service"], dtype=str)
ap = ap[ap["iata_code"].notna() & (ap["iata_code"].str.len() == 3)]
ap["rank"] = ap["type"].map({"large_airport": 0, "medium_airport": 1, "small_airport": 2}).fillna(3)
ap["rank"] -= (ap["scheduled_service"] == "yes") * 10
ap = ap.sort_values("rank").drop_duplicates("iata_code").set_index("iata_code")

# ================================================================ A. network & overlap
dep_by = df.groupby(["Origin", "Reporting_Airline"]).size().unstack(fill_value=0)
for c in CARRIERS:
    if c not in dep_by:
        dep_by[c] = 0
city = pd.concat([df[["Origin", "OriginCityName", "OriginState"]].set_axis(["code", "city", "state"], axis=1),
                  df[["Dest", "DestCityName", "DestState"]].set_axis(["code", "city", "state"], axis=1)]
                 ).drop_duplicates("code").set_index("code")
codes = sorted(set(df["Origin"]) | set(df["Dest"]))
missing_coords = [c for c in codes if c not in ap.index]
airports = pd.DataFrame({
    "code": codes,
    "city": [city.loc[c, "city"].split(",")[0] for c in codes],
    "state": [city.loc[c, "state"] for c in codes],
    "lat": [r(float(ap.loc[c, "latitude_deg"]), 4) if c in ap.index else None for c in codes],
    "lon": [r(float(ap.loc[c, "longitude_deg"]), 4) if c in ap.index else None for c in codes],
    "AS": [int(dep_by.loc[c, "AS"]) if c in dep_by.index else 0 for c in codes],
    "HA": [int(dep_by.loc[c, "HA"]) if c in dep_by.index else 0 for c in codes],
    "tz": [df.loc[df["Origin"] == c, "o_tz"].iloc[0] if (df["Origin"] == c).any()
           else df.loc[df["Dest"] == c, "d_tz"].iloc[0] for c in codes],
})

mk = df.groupby(["mkt", "Reporting_Airline"]).size().unstack(fill_value=0)
for c in CARRIERS:
    if c not in mk:
        mk[c] = 0
dist = df.groupby("mkt")["Distance"].median()
markets = mk.reset_index()
markets[["a", "b"]] = markets["mkt"].str.split("-", expand=True)
markets["miles"] = markets["mkt"].map(dist).round().astype(int)
markets["both"] = (markets["AS"] > 0) & (markets["HA"] > 0)
markets = markets.sort_values(["both", "AS", "HA"], ascending=False)
ov = markets[markets["both"]]
carrier_flights = {c: int((df["Reporting_Airline"] == c).sum()) for c in CARRIERS}
ap_sets = {c: set(df.loc[df["Reporting_Airline"] == c, "Origin"]) | set(df.loc[df["Reporting_Airline"] == c, "Dest"])
           for c in CARRIERS}
overlap = {
    "markets": {c: int((markets[c] > 0).sum()) for c in CARRIERS},
    "markets_both": int(len(ov)),
    "markets_total": int(len(markets)),
    "flights_in_overlap": {c: int(ov[c].sum()) for c in CARRIERS},
    "share_in_overlap": {c: r(ov[c].sum() / carrier_flights[c]) for c in CARRIERS},
    "airports": {c: len(ap_sets[c]) for c in CARRIERS},
    "airports_both": sorted(ap_sets["AS"] & ap_sets["HA"]),
    "airports_total": len(codes),
    "overlap_markets": [[m, int(a), int(h)] for m, a, h in ov[["mkt", "AS", "HA"]].itertuples(index=False)],
}
hubs = {}
for c in CARRIERS:
    s = dep_by[c].sort_values(ascending=False)
    tot = s.sum()
    hubs[c] = [[k, int(v), r(v / tot)] for k, v in s.head(10).items()]


def segment(row_o, row_d):
    if row_o == "HI" and row_d == "HI":
        return "inter-island"
    if "HI" in (row_o, row_d):
        return "Hawaii-mainland"
    if row_o == "AK" and row_d == "AK":
        return "intra-Alaska"
    if "AK" in (row_o, row_d):
        return "Alaska-Lower 48"
    return "Lower 48"


df["segment"] = [segment(o, d) for o, d in zip(df["OriginState"], df["DestState"])]
seg = df.groupby(["Reporting_Airline", "segment"]).size().unstack(fill_value=0)
geography = {c: {"touch_hawaii": r(df.loc[df["Reporting_Airline"] == c, "touch_hi"].mean()),
                 "touch_alaska": r(df.loc[df["Reporting_Airline"] == c, "touch_ak"].mean()),
                 "segments": {k: int(v) for k, v in seg.loc[c].items() if v > 0}} for c in CARRIERS}

# ================================================================ B. operations compared
carriers = {}
for c in CARRIERS:
    g = df[df["Reporting_Airline"] == c]
    s = ops_stats(g)
    s.update({"name": NAMES[c], "tails": int(g["Tail_Number"].nunique()),
              "airports": len(ap_sets[c]), "markets": overlap["markets"][c]})
    carriers[c] = s
combined = ops_stats(df)

df["month"] = df["date"].dt.month
mrows = []
for (m, c), g in df.groupby(["month", "Reporting_Airline"]):
    s = ops_stats(g)
    mrows.append([int(m), c, s["flights"], s["cancelled"], s["cancel_rate"], s["diverted"], s["arrived"],
                  s["otp"]["A0"], s["otp"]["A14"], s["otp"]["A30"], s["avg_arr_delay"],
                  s["cause_share"]["late_aircraft"]])
monthly = {"cols": ["month", "carrier", "flights", "cancelled", "cancel_rate", "diverted", "arrived",
                    "A0", "A14", "A30", "avg_arr_delay", "late_aircraft_share"],
           "rows": mrows, "merger_close_month": 9, "merger_close": MERGER_CLOSE}

# ================================================================ C. the worst day
df["late15"] = df["arrived"] & (df["ArrDel15"] == 1)
df["disrupted"] = (df["Cancelled"] == 1) | (df["Diverted"] == 1) | df["late15"]
day = df.groupby("FlightDate").agg(flights=("disrupted", "size"), disrupted=("disrupted", "sum"),
                                   cancelled=("Cancelled", "sum"), diverted=("Diverted", "sum"),
                                   late15=("late15", "sum"))
day["share"] = day["disrupted"] / day["flights"]
for c in CARRIERS:
    gc = df[df["Reporting_Airline"] == c].groupby("FlightDate")
    day[c + "_flights"] = gc.size()
    day[c + "_share"] = gc["disrupted"].mean()
day = day.fillna(0)
ranked = day.sort_values(["share", "disrupted"], ascending=False)
WORST = ranked.index[0]
D0 = (pd.Timestamp(WORST, tz="UTC") - EPOCH) / pd.Timedelta(minutes=1)   # 00:00 UTC of the worst day
print("worst day", WORST, ranked.iloc[0].to_dict())


def day_row(d):
    x = day.loc[d]
    return {"date": d, "flights": int(x["flights"]), "disrupted": int(x["disrupted"]),
            "share": r(x["share"]), "cancelled": int(x["cancelled"]), "diverted": int(x["diverted"]),
            "late15": int(x["late15"]), "AS_share": r(x["AS_share"]), "HA_share": r(x["HA_share"])}


W = df[df["FlightDate"] == WORST].copy()
rel = ["sdep", "adep", "sarr", "aarr", "woff", "won", "air_end"]
for c in rel:
    W[c + "_r"] = (W[c] - D0).round()
W = W.sort_values(["sdep_r", "Reporting_Airline", "fn"])
W["cancel_code"] = W["CancellationCode"].where(W["Cancelled"] == 1)
W["div_airport"] = W["Div1Airport"].where(W["Diverted"] == 1)
flight_cols_src = ["Reporting_Airline", "fn", "Tail_Number", "Origin", "Dest", "sdep_r", "adep_r", "sarr_r",
                   "aarr_r", "woff_r", "won_r", "DepDelay", "ArrDelay", "Cancelled", "Diverted", "cancel_code",
                   "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay", "div_airport"]
flight_cols = ["carrier", "flight", "tail", "origin", "dest", "sched_dep", "act_dep", "sched_arr", "act_arr",
               "wheels_off", "wheels_on", "dep_delay", "arr_delay", "cancelled", "diverted", "cancel_code",
               "carrier_delay", "weather_delay", "nas_delay", "security_delay", "late_aircraft_delay",
               "div_airport"]
wf = W[flight_cols_src].copy()
wf.columns = flight_cols
wf_table = table(wf, flight_cols)

# hourly summary (hour index h covers [60h, 60h+60) minutes after 00:00 UTC of the worst day)
h_lo = int(np.floor(W["sdep_r"].min() / 60))
h_hi = int(np.ceil(np.nanmax(W[["sarr_r", "aarr_r"]].to_numpy()) / 60))
hrows = []
for h in range(h_lo, h_hi):
    a, b = 60 * h, 60 * h + 60
    sched = W[(W["sdep_r"] >= a) & (W["sdep_r"] < b)]
    dep = W[(W["adep_r"] >= a) & (W["adep_r"] < b)]
    arr = W[(W["aarr_r"] >= a) & (W["aarr_r"] < b)]
    air = W[(W["woff_r"] < b) & (W["air_end_r"] > a)]          # in the air at some point of the hour
    hrows.append([h, len(sched), int(sched["Cancelled"].sum()), len(dep), int((dep["DepDelay"] >= 15).sum()),
                  len(arr), int((arr["ArrDelay"] >= 15).sum()), len(air)])
hourly = {"cols": ["hour_utc", "sched_dep", "cancelled", "departed", "dep_delayed15", "arrived",
                   "arr_late15", "airborne"], "rows": hrows}

# departures from each airport that day; delay figures use operated (not cancelled) departures only
Wd = W.assign(op_delay=W["DepDelay"].where(W["Cancelled"] == 0))
ad = Wd.groupby("Origin").agg(departures=("fn", "size"), cancelled=("Cancelled", "sum"),
                              dep_delayed15=("op_delay", lambda s: int((s >= 15).sum())),
                              avg_dep_delay=("op_delay", "mean"),
                              dep_delay_min=("op_delay", lambda s: s.clip(lower=0).sum()))
ad["disrupted"] = ad["cancelled"] + ad["dep_delayed15"]
ad["share"] = ad["disrupted"] / ad["departures"]
ad = ad.sort_values(["disrupted", "share"], ascending=False).head(5).reset_index()
top_airports = [{"airport": x.Origin, "departures": int(x.departures), "cancelled": int(x.cancelled),
                 "dep_delayed15": int(x.dep_delayed15), "disrupted": int(x.disrupted), "share": r(x.share),
                 "avg_dep_delay": r(x.avg_dep_delay, 1), "dep_delay_min": int(x.dep_delay_min)}
                for x in ad.itertuples()]

worst = {
    "date": WORST,
    "definition": "Disruption share = (cancelled + diverted + arrived 15+ min late) / scheduled flights, "
                  "AS+HA combined, by BTS FlightDate (local scheduled departure date). The ratio is taken on "
                  "the pooled flights, so each carrier counts in proportion to its volume.",
    "utc_zero": pd.Timestamp(WORST, tz="UTC").strftime("%Y-%m-%dT%H:%MZ"),
    "ranking": [day_row(d) for d in ranked.index[:6]],
    # transparency: the same metric ranked by absolute count, and the worst day of every month
    "worst_by_count": day_row(day.sort_values(["disrupted", "share"], ascending=False).index[0]),
    "worst_by_month": [day_row(g.sort_values(["share", "disrupted"], ascending=False).index[0])
                       for _, g in day.groupby(day.index.str[:7])],
    "by_carrier": {c: ops_stats(W[W["Reporting_Airline"] == c]) for c in CARRIERS},
    "cancel_codes": {CANCEL_CODES.get(k, k): int(v) for k, v in W["cancel_code"].value_counts().items()},
    "cancel_codes_by_carrier": {c: {CANCEL_CODES.get(k, k): int(v) for k, v in
                                    W.loc[W["Reporting_Airline"] == c, "cancel_code"].value_counts().items()}
                                for c in CARRIERS},
    "year_median_share": r(day["share"].median()),
    "flights": wf_table,
    "hourly": hourly,
    "top_airports": top_airports,
}
daily = {"cols": ["date", "flights", "disrupted", "share", "cancelled", "AS_share", "HA_share"],
         "rows": [[d, int(x.flights), int(x.disrupted), r(x.share), int(x.cancelled), r(x.AS_share), r(x.HA_share)]
                  for d, x in day.sort_index().iterrows()]}

# ================================================================ D. delay propagation
prop = {c: carriers[c]["cause_share"]["late_aircraft"] for c in CARRIERS}
op = W[(W["Cancelled"] == 0) & W["Tail_Number"].notna()].sort_values("sdep")
cands = []
for tail, g in op.groupby("Tail_Number"):
    g = g.reset_index(drop=True)
    best, best_rng = 0, None
    i = 0
    while i < len(g):
        if (g.loc[i, "ArrDelay"] >= 15) or g.loc[i, "Diverted"] == 1:
            j = i
            while j + 1 < len(g) and g.loc[j + 1, "LateAircraftDelay"] > 0:
                j += 1
            if j - i + 1 > best:
                best, best_rng = j - i + 1, (i, j)
            i = j + 1
        else:
            i += 1
    if best >= 3:
        lam = g.loc[best_rng[0]:best_rng[1], "LateAircraftDelay"].fillna(0).sum()
        cands.append((best, lam, tail, g.loc[0, "Reporting_Airline"]))
cands.sort(key=lambda t: (-t[0], -t[1]))
picked = []
for c in CARRIERS:                      # longest cascade per carrier first, then fill to 3
    for t in cands:
        if t[3] == c and t not in picked:
            picked.append(t)
            break
for t in cands:
    if len(picked) >= 3:
        break
    if t not in picked:
        picked.append(t)
chains = []
for run, lam, tail, c in picked:
    g = W[W["Tail_Number"] == tail].sort_values("sdep").reset_index(drop=True)
    legs = []
    prev = None
    for x in g.itertuples():
        legs.append([x.fn, x.Origin, x.Dest, num(x.sdep_r), num(x.adep_r), num(x.sarr_r), num(x.aarr_r),
                     num(x.DepDelay), num(x.ArrDelay), num(x.LateAircraftDelay), num(x.CarrierDelay),
                     num(x.WeatherDelay), num(x.NASDelay), int(x.Cancelled), int(x.Diverted),
                     num(x.sdep_r - prev.sarr_r) if prev is not None else None,
                     num(x.adep_r - prev.aarr_r) if prev is not None and pd.notna(x.adep_r) and pd.notna(prev.aarr_r) else None])
        prev = x
    chains.append({"tail": tail, "carrier": c, "cascade_legs": int(run), "late_aircraft_min": int(lam),
                   "legs": {"cols": ["flight", "origin", "dest", "sched_dep", "act_dep", "sched_arr", "act_arr",
                                     "dep_delay", "arr_delay", "late_aircraft_delay", "carrier_delay",
                                     "weather_delay", "nas_delay", "cancelled", "diverted",
                                     "sched_turn", "actual_turn"], "rows": legs}})
propagation = {
    "late_aircraft_share_year": prop,
    "late_aircraft_share_worst_day": {c: worst["by_carrier"][c]["cause_share"]["late_aircraft"] for c in CARRIERS},
    "tails_with_cascade_3plus": {c: sum(1 for t in cands if t[3] == c) for c in CARRIERS},
    "definition": "Cascade = a leg arriving 15+ min late (or diverted) followed by successive legs of the same "
                  "tail whose BTS LateAircraftDelay > 0. Chains export the tail's whole rotation that day.",
    "chains": chains,
}

# ================================================================ E. canonical flight-leg examples


def iso(m):
    if m is None or pd.isna(m):
        return None
    return (EPOCH + pd.Timedelta(minutes=float(m))).strftime("%Y-%m-%dT%H:%MZ")


def canon(x):
    sdate = (EPOCH + pd.Timedelta(minutes=float(x.sdep))).strftime("%Y-%m-%d")
    a14 = None if not x.arrived else bool(x.ArrDel15 == 0)
    status = "cancelled" if x.Cancelled == 1 else "diverted" if x.Diverted == 1 else "arrived"

    def off(m_local_day, utc_m):            # UTC offset in hours implied by the conversion
        return r((m_local_day - utc_m) / 60, 2)
    src = {"Reporting_Airline": x.Reporting_Airline, "Flight_Number_Reporting_Airline": x.Flight_Number_Reporting_Airline,
           "FlightDate": x.FlightDate, "Tail_Number": x.Tail_Number, "Origin": x.Origin, "Dest": x.Dest,
           "CRSDepTime": x.CRSDepTime, "DepTime": x.DepTime if isinstance(x.DepTime, str) else None,
           "CRSArrTime": x.CRSArrTime, "ArrTime": x.ArrTime if isinstance(x.ArrTime, str) else None,
           "CRSElapsedTime": num(x.CRSElapsedTime), "DepDelay": num(x.DepDelay), "ArrDelay": num(x.ArrDelay),
           "ArrDel15": num(x.ArrDel15), "Cancelled": num(x.Cancelled), "CancellationCode":
               x.CancellationCode if isinstance(x.CancellationCode, str) else None, "Diverted": num(x.Diverted)}
    can = {"leg_key": f"{x.Reporting_Airline}|{x.fn}|{sdate}|{x.Origin}",
           "operating_carrier": x.Reporting_Airline, "flight_number": int(x.fn), "sched_dep_date_utc": sdate,
           "origin": x.Origin, "dest": x.Dest, "tail": x.Tail_Number,
           "origin_tz": x.o_tz, "dest_tz": x.d_tz,
           "origin_utc_offset_h": off(x.day0 + x.CRSDepTime_m, x.sdep),
           "dest_utc_offset_h": off(x.day0 + 1440 * x.arr_k + x.CRSArrTime_m, x.sarr),
           "sched_dep_utc": iso(x.sdep), "act_dep_utc": iso(x.adep),
           "sched_arr_utc": iso(x.sarr), "act_arr_utc": iso(x.aarr),
           "arr_delay_min": num(x.ArrDelay), "status": status, "a14": a14,
           "local_date_differs": sdate != x.FlightDate}
    return {"source": src, "canonical": can}


E = W.copy()
E["sdate"] = [(EPOCH + pd.Timedelta(minutes=float(m))).strftime("%Y-%m-%d") for m in E["sdep"]]
E["datediff"] = E["sdate"] != E["FlightDate"]
picks = []


def pick(mask, order_col="sdep", asc=True):
    cand = E[mask & ~E.index.isin([p.Index for p in picks])].sort_values(order_col, ascending=asc)
    if len(cand):
        picks.append(next(cand.itertuples()))


pick((E["Reporting_Airline"] == "AS") & E["datediff"] & E["arrived"] & (E["ArrDel15"] == 0))
pick((E["Reporting_Airline"] == "AS") & E["late15"] & E["ArrDelay"].between(15, 120) & E["touch_hi"])
pick((E["Reporting_Airline"] == "AS") & (E["Cancelled"] == 1))
pick((E["Reporting_Airline"] == "HA") & E["datediff"] & E["arrived"] & (E["Origin"] == "HNL"))
pick((E["Reporting_Airline"] == "HA") & (E["segment"] == "inter-island") & E["arrived"] & (E["ArrDel15"] == 0))
pick((E["Reporting_Airline"] == "HA") & E["late15"] & E["ArrDelay"].between(15, 120))
canonical = {
    "key_format": "operating_carrier|flight_number|sched_dep_date_utc|origin",
    "a14_rule": "a14 = true when the flight arrived (not cancelled, not diverted) and ArrDelay <= 14 min "
                "(BTS ArrDel15 == 0); false when it arrived 15+ min late; null when cancelled or diverted.",
    "examples": [canon(p) for p in picks],
}
# Is the key unique? Test it on the full year, and compare with the local-date variant
# (BTS FlightDate = local scheduled departure date at the origin, the airline convention).
df["sd_utc"] = [(EPOCH + pd.Timedelta(minutes=float(m))).strftime("%Y-%m-%d") for m in df["sdep"]]
k_utc = ["Reporting_Airline", "fn", "sd_utc", "Origin"]
k_loc = ["Reporting_Airline", "fn", "FlightDate", "Origin"]
dup_u = df[df.duplicated(k_utc, keep=False)].sort_values("sdep")
canonical["key_collisions"] = {
    "utc_date_key": {"groups": int(dup_u.groupby(k_utc).ngroups), "flights": int(len(dup_u)),
                     "rows": [[x.Reporting_Airline, int(x.fn), x.FlightDate, x.CRSDepTime, x.Origin, x.Dest, x.sd_utc,
                               iso(x.sdep)] for x in dup_u.itertuples()],
                     "cols": ["carrier", "flight", "local_date", "local_dep", "origin", "dest",
                              "sched_dep_date_utc", "sched_dep_utc"]},
    "local_date_key": {"groups": int(df[df.duplicated(k_loc, keep=False)].groupby(k_loc).ngroups)},
    "flights_tested": int(len(df)),
}
# local-date vs UTC-date differences across the whole year
df["sdate_utc_day"] = (df["sdep"] // 1440).astype(int)
diff_share = {c: r((df.loc[df["Reporting_Airline"] == c, "sdate_utc_day"] * 1440 !=
                    df.loc[df["Reporting_Airline"] == c, "day0"]).mean()) for c in CARRIERS}
canonical["share_local_date_ne_utc_date"] = diff_share

# ================================================================ assemble
out = {
    "meta": {
        "source": "BTS Reporting Carrier On-Time Performance (1987-present), 2024; OurAirports airports.csv",
        "carriers": NAMES, "year": 2024, "months_loaded": months, "flights": int(len(df)),
        "merger_close": MERGER_CLOSE,
        "scope_note": "BTS on-time data covers each reporting carrier's own domestic scheduled flights. "
                      "Alaska's regional partners (Horizon QX, SkyWest OO) and all international flights are "
                      "not included. Hawaiian kept reporting separately through 2024.",
        "time_check": tz_check, "missing_coords": missing_coords,
    },
    "carriers": carriers,
    "combined": combined,
    "network": {"airports": table(airports, ["code", "city", "state", "lat", "lon", "AS", "HA", "tz"]),
                "markets": table(markets, ["a", "b", "AS", "HA", "miles"]),
                "overlap": overlap, "hubs": hubs, "geography": geography},
    "monthly": monthly,
    "daily": daily,
    "worst_day": worst,
    "propagation": propagation,
    "canonical": canonical,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
txt = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
OUT.write_text("/* generated by analysis/airline_bts.py: do not edit by hand */\n"
               f"window.DATA_AIRLINE_REAL = {txt};\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
