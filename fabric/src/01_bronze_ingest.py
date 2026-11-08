# %% [markdown]
# # 01 · Bronze: land the raw BTS on-time files
#
# **Lakehouse:** `airline_lakehouse` (attach it as the default lakehouse before running).
#
# Bronze keeps the data **exactly as BTS publishes it**: every carrier, every column, every value as text.
# Nothing is cleaned here. Later layers can always be rebuilt from bronze.
#
# 1. Download the 12 monthly 2024 zips from BTS (skipped if a file is already in `Files/landing/bts/`).
# 2. Unzip each month's CSV.
# 3. Read them with Spark, add lineage columns (`_source_file`, `_ingested_at`) and save the Delta table `bronze_bts_ontime`.
# 4. Log row counts per file in `bronze_ingest_log`, so every later number can be traced back to a file.
#
# Source: Bureau of Transportation Statistics, *Reporting Carrier On-Time Performance (1987-present)*. US public domain.

# %% tags=["parameters"]
YEAR = 2024
MONTHS = list(range(1, 13))
FILES_API = "/lakehouse/default/Files"   # file-system path of the default lakehouse (Python file I/O)
FILES = "Files"                          # the same folder as Spark sees it

# %%
import os
import urllib.request
import zipfile
from datetime import datetime, timezone

from pyspark.sql import functions as F

BTS_URL = ("https://transtats.bts.gov/PREZIP/"
           "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{y}_{m}.zip")
ZIP_DIR = f"{FILES_API}/landing/bts/zips"
CSV_DIR = f"{FILES_API}/landing/bts/csv"
os.makedirs(ZIP_DIR, exist_ok=True)
os.makedirs(CSV_DIR, exist_ok=True)

for m in MONTHS:
    zpath = f"{ZIP_DIR}/bts_{YEAR}_{m}.zip"
    if os.path.exists(zpath) and os.path.getsize(zpath) > 1_000_000:
        print(f"{YEAR}-{m:02d}: zip already landed")
        continue
    print(f"{YEAR}-{m:02d}: downloading ...")
    req = urllib.request.Request(BTS_URL.format(y=YEAR, m=m), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(zpath, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)

# %%
# Unzip: each BTS zip holds one CSV (plus a readme). Keep one CSV per month with a predictable name.
for m in MONTHS:
    out = f"{CSV_DIR}/bts_ontime_{YEAR}_{m:02d}.csv"
    if os.path.exists(out):
        continue
    with zipfile.ZipFile(f"{ZIP_DIR}/bts_{YEAR}_{m}.zip") as z:
        member = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(member) as src, open(out, "wb") as dst:
            while chunk := src.read(1 << 22):
                dst.write(chunk)
    print("unzipped", os.path.basename(out))

# %%
# Read every month as text. BTS rows end with a trailing comma, which Spark reads as an
# empty unnamed column (_c109); it carries no data, so it is dropped.
paths = [f"{FILES}/landing/bts/csv/bts_ontime_{YEAR}_{m:02d}.csv" for m in MONTHS]
raw = (spark.read
       .option("header", True)
       .option("inferSchema", False)       # bronze keeps every value as text
       .csv(paths))
raw = raw.drop(*[c for c in raw.columns if c.startswith("_c")])

ingested_at = datetime.now(timezone.utc).replace(microsecond=0)
bronze = (raw
          .withColumn("_source_file", F.regexp_extract(F.input_file_name(), r"([^/]+\.csv)$", 1))
          .withColumn("_ingested_at", F.lit(ingested_at).cast("timestamp")))

(bronze.write.format("delta").mode("overwrite")
       .option("overwriteSchema", "true")
       .partitionBy("Month")
       .saveAsTable("bronze_bts_ontime"))
print(f"bronze_bts_ontime: {len(bronze.columns)} columns")

# %%
# Ingestion log: one row per file. Every later count can be traced back to these numbers.
log = (spark.read.table("bronze_bts_ontime")
       .groupBy("_source_file")
       .agg(F.count("*").alias("rows"),
            F.countDistinct("Reporting_Airline").alias("carriers"),
            F.sum(F.when(F.col("Reporting_Airline").isin("AS", "HA"), 1).otherwise(0)).alias("rows_as_ha"),
            F.min("FlightDate").alias("first_date"),
            F.max("FlightDate").alias("last_date"))
       .withColumn("_ingested_at", F.lit(ingested_at).cast("timestamp"))
       .orderBy("_source_file"))
log.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("bronze_ingest_log")
log.show(truncate=False)

totals = log.agg(F.sum("rows").alias("rows"), F.sum("rows_as_ha").alias("rows_as_ha")).first()
print(f"Bronze holds {totals['rows']:,} flights from all carriers; {totals['rows_as_ha']:,} are Alaska or Hawaiian.")
