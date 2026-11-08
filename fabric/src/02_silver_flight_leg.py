# %% [markdown]
# # 02 · Silver: one clean, conformed row per flight leg
#
# Silver turns raw BTS text into the **canonical flight leg** from the course design (BUAN 6335),
# for the two carriers of the real merger: **Alaska (AS)** and **Hawaiian (HA)**.
#
# * Types are cast, and BTS local clock times (`hhmm` at each airport) become **UTC timestamps**.
#   Each airport gets an IANA time zone, so 2024 daylight-saving rules are applied correctly.
# * Each leg gets the key recommended in the portfolio (chapter 10): **carrier | flight | scheduled departure in UTC | origin**.
# * Flags for the on-time standard **A14** (arrived 14 minutes late or less), cancellations and diversions.
# * **Data-quality checks** are saved in `silver_dq_checks`. Run this notebook again and the checks run again.
#
# Outputs: `silver_flight_leg`, `silver_airport`, `silver_dq_checks`.

# %% tags=["parameters"]
CARRIERS = ["AS", "HA"]
FILES_API = "/lakehouse/default/Files"
FILES = "Files"
OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

# %%
import os
import urllib.request

from pyspark.sql import functions as F

spark.conf.set("spark.sql.session.timeZone", "UTC")   # every timestamp below is shown in UTC

# OurAirports (public domain) gives each airport its coordinates.
ap_path = f"{FILES_API}/landing/ourairports/airports.csv"
if not os.path.exists(ap_path):
    os.makedirs(os.path.dirname(ap_path), exist_ok=True)
    urllib.request.urlretrieve(OURAIRPORTS_URL, ap_path)
    print("downloaded OurAirports airports.csv")

# %%
# Time zones. BTS gives local clock times, so each airport needs its IANA zone:
# the state's zone, with overrides for airports in states that span two zones.
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
AIRPORT_TZ = {"ADK": "America/Adak", "ELP": DEN, "PNS": CHI, "VPS": CHI, "ECP": CHI, "LWS": LA,
              "TYS": NY, "TRI": NY, "CHA": NY, "RAP": DEN, "DIK": DEN, "ISN": CHI, "PPG": "Pacific/Pago_Pago",
              "SPN": "Pacific/Saipan", "GUM": "Pacific/Guam", "IMT": CHI, "EKO": LA}


def as_map(d):
    return F.create_map(*[F.lit(x) for kv in d.items() for x in kv])


state_tz, airport_tz = as_map(STATE_TZ), as_map(AIRPORT_TZ)


def zone(code_col, state_col):
    return F.coalesce(airport_tz[F.col(code_col)], state_tz[F.col(state_col)])


def clock_min(c):
    """BTS 'hhmm' text -> minutes after local midnight (2400 -> 1440)."""
    v = F.col(c).cast("int")
    return F.floor(v / 100) * 60 + v % 100


def local_ts(day_offset, minutes):
    """FlightDate + days + minutes, as a wall-clock timestamp (time zone not applied yet)."""
    return F.timestamp_seconds(F.unix_timestamp(F.col("FlightDate"), "yyyy-MM-dd")
                               + day_offset * 86400 + minutes * 60)


def plus_min(ts, minutes):
    return F.timestamp_seconds(F.unix_timestamp(ts) + minutes * 60)

# %%
NUMERIC = ["DepDelay", "DepDel15", "TaxiOut", "TaxiIn", "ArrDelay", "ArrDel15", "Cancelled", "Diverted",
           "CRSElapsedTime", "ActualElapsedTime", "AirTime", "Distance", "CarrierDelay", "WeatherDelay",
           "NASDelay", "SecurityDelay", "LateAircraftDelay", "DivReachedDest", "DivArrDelay"]

b = spark.read.table("bronze_bts_ontime").where(F.col("Reporting_Airline").isin(CARRIERS))
for c in NUMERIC:
    b = b.withColumn(c, F.col(c).cast("double"))

s = (b
     .withColumn("flight_number", F.col("Flight_Number_Reporting_Airline").cast("int"))
     .withColumn("flight_date_local", F.to_date("FlightDate"))
     .withColumn("origin_tz", zone("Origin", "OriginState"))
     .withColumn("dest_tz", zone("Dest", "DestState"))
     .withColumn("crs_dep_m", clock_min("CRSDepTime"))
     .withColumn("crs_arr_m", clock_min("CRSArrTime"))
     .withColumn("dep_m", clock_min("DepTime")))

# Scheduled departure: local date = FlightDate, local clock = CRSDepTime at the origin.
s = s.withColumn("sched_dep_utc", F.to_utc_timestamp(local_ts(0, F.col("crs_dep_m")), F.col("origin_tz")))
# Scheduled arrival: CRSArrTime is local at the destination and may fall on the next day.
# The scheduled block time (CRSElapsedTime) tells how many days to add.
guess = F.to_utc_timestamp(local_ts(0, F.col("crs_arr_m")), F.col("dest_tz"))
want = plus_min(F.col("sched_dep_utc"), F.coalesce(F.col("CRSElapsedTime"), F.lit(0)))
s = (s.withColumn("arr_day_offset", F.round((F.unix_timestamp(want) - F.unix_timestamp(guess)) / 86400).cast("int"))
      .withColumn("sched_arr_utc", F.to_utc_timestamp(local_ts(F.col("arr_day_offset"), F.col("crs_arr_m")),
                                                      F.col("dest_tz"))))

# Actual times = scheduled + reported delay. A cancelled flight never departs.
cancelled = F.col("Cancelled") == 1
arr_delay = F.when(F.col("Diverted") == 0, F.col("ArrDelay")).when(F.col("DivReachedDest") == 1, F.col("DivArrDelay"))
s = (s.withColumn("act_dep_utc", F.when(~cancelled, plus_min(F.col("sched_dep_utc"), F.col("DepDelay"))))
      .withColumn("act_arr_utc", F.when(~cancelled, plus_min(F.col("sched_arr_utc"), arr_delay))))

arrived = (F.col("Cancelled") == 0) & (F.col("Diverted") == 0) & F.col("ArrDelay").isNotNull()
s = (s
     .withColumn("status", F.when(cancelled, "cancelled").when(F.col("Diverted") == 1, "diverted").otherwise("arrived"))
     .withColumn("arrived", arrived)
     .withColumn("a14", F.when(arrived, F.col("ArrDel15") == 0))          # null when cancelled or diverted
     .withColumn("late15", arrived & (F.col("ArrDel15") == 1))
     .withColumn("disrupted", cancelled | (F.col("Diverted") == 1) | (arrived & (F.col("ArrDel15") == 1)))
     .withColumn("market", F.concat_ws("-", F.least("Origin", "Dest"), F.greatest("Origin", "Dest")))
     .withColumn("segment",
                 F.when((F.col("OriginState") == "HI") & (F.col("DestState") == "HI"), "inter-island")
                  .when((F.col("OriginState") == "HI") | (F.col("DestState") == "HI"), "Hawaii-mainland")
                  .when((F.col("OriginState") == "AK") & (F.col("DestState") == "AK"), "intra-Alaska")
                  .when((F.col("OriginState") == "AK") | (F.col("DestState") == "AK"), "Alaska-Lower 48")
                  .otherwise("Lower 48"))
     # the recommended key (portfolio chapter 10) and the original design key, kept for the check below
     .withColumn("leg_key", F.concat_ws("|", "Reporting_Airline", "flight_number",
                                        F.date_format("sched_dep_utc", "yyyy-MM-dd'T'HH:mm'Z'"), "Origin"))
     .withColumn("leg_key_utc_date", F.concat_ws("|", "Reporting_Airline", "flight_number",
                                                 F.date_format("sched_dep_utc", "yyyy-MM-dd"), "Origin"))
     .withColumn("month", F.month("flight_date_local")))

# check columns (used by the data-quality cell)
s = (s.withColumn("_elapsed_resid", (F.unix_timestamp("sched_arr_utc") - F.unix_timestamp("sched_dep_utc")) / 60
                  - F.col("CRSElapsedTime"))
      .withColumn("_dep_clock_ok", F.when(F.col("DepDelay").isNotNull() & F.col("dep_m").isNotNull(),
                                          F.pmod(F.col("crs_dep_m") + F.col("DepDelay"), F.lit(1440))
                                          == F.pmod(F.col("dep_m"), F.lit(1440)))))
s = s.cache()

# %%
silver = s.select(
    "leg_key", F.col("Reporting_Airline").alias("carrier"), "flight_number",
    F.col("Tail_Number").alias("tail"), F.col("Origin").alias("origin"), F.col("Dest").alias("dest"),
    "market", "segment", "flight_date_local", "month", "origin_tz", "dest_tz",
    "sched_dep_utc", "act_dep_utc", "sched_arr_utc", "act_arr_utc",
    F.col("DepDelay").alias("dep_delay_min"), F.col("ArrDelay").alias("arr_delay_min"),
    "status", "arrived", "a14", "late15", "disrupted",
    F.col("CancellationCode").alias("cancel_code"),
    F.col("Distance").alias("distance_mi"), F.col("CRSElapsedTime").alias("sched_block_min"),
    F.col("CarrierDelay").alias("carrier_delay_min"), F.col("WeatherDelay").alias("weather_delay_min"),
    F.col("NASDelay").alias("nas_delay_min"), F.col("SecurityDelay").alias("security_delay_min"),
    F.col("LateAircraftDelay").alias("late_aircraft_delay_min"),
    "_source_file")
(silver.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
       .partitionBy("month").saveAsTable("silver_flight_leg"))

# Airport dimension: code, city and state from BTS, coordinates from OurAirports.
ap = (spark.read.option("header", True).csv(f"{FILES}/landing/ourairports/airports.csv")
      .where(F.length("iata_code") == 3)
      .withColumn("_rank", F.when(F.col("scheduled_service") == "yes", -10).otherwise(0)
                  + F.when(F.col("type") == "large_airport", 0).when(F.col("type") == "medium_airport", 1)
                     .when(F.col("type") == "small_airport", 2).otherwise(3)))
best = ap.groupBy("iata_code").agg(F.min_by(F.struct("name", "latitude_deg", "longitude_deg"), "_rank").alias("a"))
ends = (s.select(F.col("Origin").alias("code"), F.col("OriginCityName").alias("city"),
                 F.col("OriginState").alias("state"), F.col("origin_tz").alias("tz"))
         .unionByName(s.select(F.col("Dest").alias("code"), F.col("DestCityName").alias("city"),
                               F.col("DestState").alias("state"), F.col("dest_tz").alias("tz")))
         .dropDuplicates(["code"]))
airport = (ends.join(best, ends.code == best.iata_code, "left")
               .select("code", F.split("city", ",")[0].alias("city"), "state", "tz",
                       F.col("a.name").alias("airport_name"),
                       F.col("a.latitude_deg").cast("double").alias("lat"),
                       F.col("a.longitude_deg").cast("double").alias("lon")))
airport.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_airport")
print(f"silver_flight_leg: {silver.count():,} legs · silver_airport: {airport.count()} airports")

# %%
# Data-quality checks. "expected" is what a correct pipeline must give; informational rows have none.
n_bronze = spark.read.table("bronze_bts_ontime").where(F.col("Reporting_Airline").isin(CARRIERS)).count()
leg = spark.read.table("silver_flight_leg")
apt = spark.read.table("silver_airport")


def dup_groups(col):
    return s.groupBy(col).count().where("count > 1").count()


checks = [
    ("AS/HA rows in bronze = legs in silver", leg.count(), n_bronze, "nothing lost or duplicated"),
    ("airports without a time zone", s.where(F.col("origin_tz").isNull() | F.col("dest_tz").isNull()).count(), 0,
     "every airport needs an IANA zone"),
    ("sched arrival - sched departure != CRSElapsedTime", s.where(F.col("_elapsed_resid") != 0).count(), 0,
     "proves the time-zone conversion"),
    ("computed departure clock != DepTime", s.where(F.col("_dep_clock_ok") == False).count(), 0,  # noqa: E712
     "proves actual = scheduled + delay"),
    ("duplicate leg_key (UTC timestamp key)", dup_groups("leg_key"), 0, "the recommended key is unique"),
    ("duplicate design key (UTC date only)", dup_groups("leg_key_utc_date"), None,
     "informational: the original design key collides (portfolio chapter 10)"),
    ("airports without coordinates", apt.where(F.col("lat").isNull()).count(), 0, "needed for the network map"),
    ("cancelled legs with an actual time", leg.where((F.col("status") == "cancelled")
                                                    & (F.col("act_dep_utc").isNotNull()
                                                       | F.col("act_arr_utc").isNotNull())).count(), 0,
     "a cancelled flight never departs"),
]
dq = None
for name, v, e, note in checks:            # built with Spark expressions: no Python UDFs or workers needed
    row = spark.range(1).select(
        F.lit(name).alias("check"), F.lit(int(v)).cast("long").alias("value"),
        F.lit(None if e is None else int(e)).cast("long").alias("expected"),
        F.lit(None if e is None else int(v) == int(e)).cast("boolean").alias("passed"),
        F.lit(note).alias("note"))
    dq = row if dq is None else dq.unionByName(row)
dq.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_dq_checks")
dq.show(truncate=False)
failed = [r["check"] for r in dq.collect() if r["passed"] is False]
assert not failed, f"data-quality checks failed: {failed}"
print("All data-quality checks passed.")
