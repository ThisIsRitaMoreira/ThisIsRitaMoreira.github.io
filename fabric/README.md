# Airline lakehouse in Microsoft Fabric

A bronze → silver → gold lakehouse for the real 2024 flights of **Alaska Airlines (AS)** and
**Hawaiian Airlines (HA)**, the merger that closed on 2024-09-18. It puts the platform design
from BUAN 6335 (canonical flight leg, A14 on-time standard, data-quality checks) on the real data
used in the portfolio's airline capsule.

| Layer | Notebook | Tables |
|---|---|---|
| Bronze | `01_bronze_ingest` | `bronze_bts_ontime` (every 2024 BTS row, all carriers, as text), `bronze_ingest_log` |
| Silver | `02_silver_flight_leg` | `silver_flight_leg` (AS + HA, typed, UTC times, leg key, A14 flags), `silver_airport`, `silver_dq_checks` |
| Gold | `03_gold_kpis` | `gold_carrier_month_kpi`, `gold_carrier_kpi`, `gold_daily_disruption`, `gold_market_overlap`, `gold_delay_cause`, `gold_portfolio_reconciliation` |

`sql/gold_queries.sql` has T-SQL queries for the lakehouse's SQL analytics endpoint.

**Data:** BTS *Reporting Carrier On-Time Performance (1987-present)*, 2024, all 12 months (US public domain);
OurAirports `airports.csv` (public domain). The bronze notebook downloads both itself.

## Run it in Fabric (about 20 minutes)

**Status:** the notebooks are written for a Fabric lakehouse and were tested end to end on PySpark 3.5,
the Spark version of Fabric Runtime 1.3 (see the next section). They have not yet been run inside Fabric itself.

You need a workspace on Fabric capacity (a paid F SKU or the 60-day Fabric trial). Some organizations
turn off trials or workspace creation; in that case, use a personal workspace switched to a Fabric
capacity, or ask the Fabric admin.

1. **Workspace.** *Workspaces* › **+ New workspace** › name it `Airline lakehouse` ›
   *Advanced* › a Fabric or Fabric Trial capacity › *Apply*.
2. **Lakehouse.** In the workspace: **+ New item** › **Lakehouse** › name it
   `airline_lakehouse` (leave *Lakehouse schemas* unticked) › *Create*.
3. **Import the notebooks.** In the workspace: **Import** › **Notebook** › **From this computer** ›
   select the three files in `notebooks/`.
4. **Attach the lakehouse.** Open `01_bronze_ingest`. In the *Explorer* pane:
   **Add data items** › **Existing data source** › `airline_lakehouse` › *Add*. Do the same in the other two notebooks.
5. **Run them in order** with **Run all**, and check the last cell of each:
   * `01_bronze_ingest` downloads about 340 MB from BTS and ends with
     *"Bronze holds 7,079,061 flights from all carriers; 324,349 are Alaska or Hawaiian."*
   * `02_silver_flight_leg` ends with the data-quality table and *"All data-quality checks passed."*
   * `03_gold_kpis` ends with the reconciliation table and *"17 of 17 figures match the portfolio."*
6. **Query it.** Open the lakehouse's *SQL analytics endpoint* and run the queries in `sql/gold_queries.sql`.

If BTS blocks the download in step 5, upload the 12 zips by hand instead:
lakehouse › *Files* › create folders `landing/bts/zips` › **Upload** › files named `bts_2024_1.zip` … `bts_2024_12.zip`.
The notebook skips the download when the files are already there.

## Run it on a laptop (how it was tested)

The same notebooks run on plain PySpark 3.5 (Fabric Runtime 1.3 runs Spark 3.5):

    python -I tools/build_notebooks.py src notebooks
    python -I tools/run_local.py notebooks <local lakehouse dir> <folder with bts_2024_*.zip> <airports.csv> <results.json>

`run_local.py` changes two things only: local folder paths in place of the lakehouse paths, and
temporary views in place of Delta tables (Delta writes on Windows need extra Hadoop binaries).
The notebook code itself runs unchanged.

Edit the notebooks in `src/*.py` (percent format) and rebuild the `.ipynb` files with `build_notebooks.py`.
