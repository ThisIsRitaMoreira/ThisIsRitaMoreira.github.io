# %% [markdown]
# # 03 · Gold: the business tables
#
# Gold answers the questions the operations and integration teams ask, in tables a Power BI
# report (Direct Lake) or the SQL endpoint can read directly:
#
# | Table | Question it answers |
# |---|---|
# | `gold_carrier_month_kpi` | How reliable is each airline, month by month, before and after the merger closed (2024-09-18)? |
# | `gold_carrier_kpi` | The same for the full year, per airline and combined |
# | `gold_daily_disruption` | Which days broke the operation? |
# | `gold_market_overlap` | Where do the two networks compete today? |
# | `gold_delay_cause` | Whose fault are the delay minutes: carrier, weather, air traffic system, or the late aircraft before? |
#
# The last cell **reconciles** the lakehouse with the portfolio, which computed the same figures
# separately in pandas. Two independent pipelines giving the same answer is the test.
#
# **On-time standard A14:** share of arrived flights (not cancelled, not diverted) that arrived 14 minutes late or less.

# %%
from pyspark.sql import functions as F
from pyspark.sql.window import Window

spark.conf.set("spark.sql.session.timeZone", "UTC")
leg = spark.read.table("silver_flight_leg")
both = leg.withColumn("carrier", F.lit("AS+HA"))
legs = leg.unionByName(both)            # every KPI below exists per airline and for the two combined

CAUSES = {"carrier": "carrier_delay_min", "weather": "weather_delay_min", "nas": "nas_delay_min",
          "security": "security_delay_min", "late_aircraft": "late_aircraft_delay_min"}


def kpis(df, keys):
    arr = F.col("arrived")
    out = (df.groupBy(*keys).agg(
        F.count("*").alias("flights"),
        F.sum((F.col("status") == "cancelled").cast("int")).alias("cancelled"),
        F.sum((F.col("status") == "diverted").cast("int")).alias("diverted"),
        F.sum(arr.cast("int")).alias("arrived"),
        F.avg(F.when(arr, (F.col("arr_delay_min") <= 0).cast("int"))).alias("a0"),
        F.avg(F.when(arr, F.col("a14").cast("int"))).alias("a14"),
        F.avg(F.when(arr, (F.col("arr_delay_min") <= 30).cast("int"))).alias("a30"),
        F.avg(F.when(arr, F.col("arr_delay_min"))).alias("avg_arr_delay_min"),
        *[F.sum(F.coalesce(F.col(c), F.lit(0))).alias(f"{k}_min") for k, c in CAUSES.items()]))
    total = sum(F.col(f"{k}_min") for k in CAUSES)
    return (out.withColumn("cancel_rate", F.col("cancelled") / F.col("flights"))
               .withColumn("late_aircraft_share", F.col("late_aircraft_min") / total))


def save(df, name):
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)
    print(f"{name}: {df.count():,} rows")

# %%
phase = (F.when(F.col("month") < 9, "before close")
          .when(F.col("month") == 9, "closing month")
          .otherwise("after close"))
save(kpis(legs, ["carrier", "month"]).withColumn("merger_phase", phase).orderBy("carrier", "month"),
     "gold_carrier_month_kpi")
save(kpis(legs, ["carrier"]).orderBy("carrier"), "gold_carrier_kpi")

# %%
daily = (legs.groupBy("carrier", F.col("flight_date_local").alias("date")).agg(
            F.count("*").alias("flights"),
            F.sum((F.col("status") == "cancelled").cast("int")).alias("cancelled"),
            F.sum((F.col("status") == "diverted").cast("int")).alias("diverted"),
            F.sum(F.col("late15").cast("int")).alias("late15"),
            F.sum(F.col("disrupted").cast("int")).alias("disrupted"))
         .withColumn("disruption_share", F.col("disrupted") / F.col("flights")))
rank = F.row_number().over(Window.partitionBy("carrier").orderBy(F.desc("disruption_share"), F.desc("disrupted")))
save(daily.withColumn("worst_day_rank", rank), "gold_daily_disruption")

# %%
mk = (leg.groupBy("market").pivot("carrier", ["AS", "HA"]).count().na.fill(0)
         .join(leg.groupBy("market").agg(F.percentile_approx("distance_mi", 0.5).alias("miles")), "market")
         .withColumn("both_carriers", (F.col("AS") > 0) & (F.col("HA") > 0))
         .withColumnRenamed("AS", "as_flights").withColumnRenamed("HA", "ha_flights")
         .orderBy(F.desc("both_carriers"), F.desc("as_flights")))
save(mk, "gold_market_overlap")

cause = (kpis(legs, ["carrier"])
         .select("carrier", F.explode(F.array(*[F.struct(F.lit(k).alias("cause"), F.col(f"{k}_min").alias("minutes"))
                                                 for k in CAUSES])).alias("c"))
         .select("carrier", "c.cause", "c.minutes"))
tot = cause.groupBy("carrier").agg(F.sum("minutes").alias("_t"))
save(cause.join(tot, "carrier").withColumn("share", F.col("minutes") / F.col("_t")).drop("_t")
          .orderBy("carrier", F.desc("minutes")), "gold_delay_cause")

# %%
# Reconciliation with the portfolio (pandas pipeline, analysis/airline_bts.py -> data/airline_real.js).
EXPECTED = [
    ("AS flights", "AS", "flights", 245819, 0), ("HA flights", "HA", "flights", 78530, 0),
    ("AS+HA flights", "AS+HA", "flights", 324349, 0),
    ("AS A14", "AS", "a14", 0.7793, 4), ("HA A14", "HA", "a14", 0.8455, 4), ("AS+HA A14", "AS+HA", "a14", 0.7954, 4),
    ("AS A0", "AS", "a0", 0.5858, 4), ("HA A0", "HA", "a0", 0.5705, 4),
    ("AS cancel rate", "AS", "cancel_rate", 0.0196, 4), ("HA cancel rate", "HA", "cancel_rate", 0.0105, 4),
    ("AS avg arrival delay", "AS", "avg_arr_delay_min", 4.5, 1), ("HA avg arrival delay", "HA", "avg_arr_delay_min", 4.2, 1),
    ("AS late-aircraft share", "AS", "late_aircraft_share", 0.3993, 4),
    ("HA late-aircraft share", "HA", "late_aircraft_share", 0.3505, 4),
]
year = {r["carrier"]: r for r in spark.read.table("gold_carrier_kpi").collect()}
rows = [(name, float(round(year[c][col], d)), float(exp), round(year[c][col], d) == exp) for name, c, col, exp, d in EXPECTED]

mo = spark.read.table("gold_market_overlap")
rows.append(("markets flown by both", float(mo.where("both_carriers").count()), 12.0, mo.where("both_carriers").count() == 12))
rows.append(("markets in total", float(mo.count()), 228.0, mo.count() == 228))
worst = (spark.read.table("gold_daily_disruption").where("carrier = 'AS+HA' AND worst_day_rank = 1").first())
rows.append((f"worst day share ({worst['date']})", float(round(worst["disruption_share"], 4)), 0.6039,
             str(worst["date"]) == "2024-01-17" and round(worst["disruption_share"], 4) == 0.6039))

rec = None
for name, got, exp, ok in rows:            # built with Spark expressions: no Python UDFs or workers needed
    row = spark.range(1).select(F.lit(name).alias("check"), F.lit(got).cast("double").alias("lakehouse"),
                                F.lit(exp).cast("double").alias("portfolio"), F.lit(bool(ok)).alias("matches"))
    rec = row if rec is None else rec.unionByName(row)
rec.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold_portfolio_reconciliation")
rec.show(truncate=False)
print(f"{sum(r[3] for r in rows)} of {len(rows)} figures match the portfolio.")
