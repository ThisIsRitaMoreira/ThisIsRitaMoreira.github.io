"""Run the Fabric notebooks on a laptop with plain PySpark 3.5 (the Spark version of Fabric Runtime 1.3).

What changes locally, and only here:
  * the notebooks' parameters cell is followed by local paths for FILES_API / FILES;
  * DataFrameWriter.saveAsTable registers a temporary view instead of writing Delta
    (Delta on Windows needs extra Hadoop binaries), so later notebooks read the same tables by name.
Everything else is the notebook code, unchanged, cell by cell.

Usage:
  python -I fabric/tools/run_local.py <notebooks dir> <local lakehouse dir> <bts zip dir> <airports.csv> <results.json>
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

NB_DIR, LH, ZIPS, AIRPORTS, RESULTS = (Path(a).resolve() for a in sys.argv[1:6])
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)

files = LH / "Files"
(files / "landing/bts/zips").mkdir(parents=True, exist_ok=True)
(files / "landing/ourairports").mkdir(parents=True, exist_ok=True)
for z in ZIPS.glob("bts_*.zip"):                       # pretend the downloads already happened
    dst = files / "landing/bts/zips" / z.name
    if not dst.exists():
        shutil.copyfile(z, dst)
if not (files / "landing/ourairports/airports.csv").exists():
    shutil.copyfile(AIRPORTS, files / "landing/ourairports/airports.csv")

import pyspark  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql.readwriter import DataFrameWriter  # noqa: E402

# Spark's Python worker processes must be able to import pyspark too (it may live outside site-packages)
os.environ["PYTHONPATH"] = os.pathsep.join(p for p in [str(Path(pyspark.__file__).resolve().parents[1]),
                                                       os.environ.get("PYTHONPATH", "")] if p)

spark = (SparkSession.builder.master("local[*]").appName("fabric-local-test")
         .config("spark.driver.memory", "8g")
         .config("spark.sql.shuffle.partitions", "32")
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.ui.enabled", "false")
         .getOrCreate())
spark.sparkContext.setLogLevel("ERROR")


def fake_save_as_table(self, name, *args, **kwargs):
    df = self._df
    df.createOrReplaceTempView(name)


DataFrameWriter.saveAsTable = fake_save_as_table

LOCAL = {"FILES_API": files.as_posix(), "FILES": files.as_posix()}
log = []
for nb_path in sorted(NB_DIR.glob("*.ipynb")):
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    ns = {"spark": spark, "__name__": "__main__"}
    t0 = time.time()
    print(f"\n===== {nb_path.name} =====", flush=True)
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        exec(compile("".join(cell["source"]), f"{nb_path.name}:{cell['id']}", "exec"), ns)
        if "parameters" in cell.get("metadata", {}).get("tags", []):
            ns.update(LOCAL)
    log.append({"notebook": nb_path.name, "seconds": round(time.time() - t0, 1)})
    print(f"----- {nb_path.name} done in {time.time() - t0:.0f}s", flush=True)


# ---- collect what the portfolio shows -------------------------------------------------------
def rows(name, order=None):
    df = spark.read.table(name)
    if order:
        df = df.orderBy(*order)
    out = []
    for r in df.collect():
        d = r.asDict()
        out.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()})
    return out


tables = {}
for name in ["bronze_bts_ontime", "bronze_ingest_log", "silver_flight_leg", "silver_airport", "silver_dq_checks",
             "gold_carrier_month_kpi", "gold_carrier_kpi", "gold_daily_disruption", "gold_market_overlap",
             "gold_delay_cause", "gold_portfolio_reconciliation"]:
    df = spark.read.table(name)
    tables[name] = {"rows": df.count(), "columns": len(df.columns)}

res = {
    "engine": f"PySpark {spark.version} (local), the Spark version of Fabric Runtime 1.3",
    "run_log": log,
    "tables": tables,
    "ingest_log": rows("bronze_ingest_log", ["_source_file"]),
    "dq_checks": rows("silver_dq_checks"),
    "reconciliation": rows("gold_portfolio_reconciliation"),
    "carrier_kpi": rows("gold_carrier_kpi", ["carrier"]),
    "silver_columns": spark.read.table("silver_flight_leg").columns,
    "silver_sample": rows("silver_flight_leg")[:0],
}
sample = (spark.read.table("silver_flight_leg")
          .where("leg_key IN ('AS|1|2024-01-17T15:00Z|SEA')").collect())
first = spark.read.table("silver_flight_leg").where("flight_date_local = '2024-01-17' AND carrier = 'HA'").limit(1).collect()
res["silver_sample"] = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.asDict().items()}
                        for r in (sample or first)]
RESULTS.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
print(f"\nresults -> {RESULTS}")
spark.stop()
