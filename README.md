# Rita Moreira · data portfolio

**Not published yet.** To put it online with GitHub Pages later: make the repository public, rename it
`ThisIsRitaMoreira.github.io`, and the site appears at <https://thisisritamoreira.github.io/>.

I'm Rita, a Business Analytics & AI master's student at UT Dallas (graduating August 2027), with
experience in HR operations at ALTEN and store operations at Intermarché. This portfolio shows the same
skills in four different industries. Each "capsule" tells one story: the business problem, the data, the
analysis, what it means and what I'd do about it. Every chart is built from real public data or from my
course projects, and each panel says which (real, simulated or synthetic).

| Capsule | What it shows | Data | Tools |
|---|---|---|---|
| **People analytics** (ALTEN experience) | HR service-desk SLAs and backlog, repeat tickets, merging an acquired company's HR data, an attrition study in R | UCI ServiceNow incident log (real), IBM HR attrition sample | SQL, Python, R, Excel |
| **Retail & grocery** (Intermarché experience) | Order-day priority board, stock audits, an order recommender, what promotions really sell, market baskets, an Excel Solver order plan | 84.51° *The Complete Journey* (2,469 households, real) | Power BI/DAX logic, Python, Excel Solver, [Tableau Public dashboard](https://public.tableau.com/app/profile/rita.sofia.ferreira.moreira/viz/Promoperformancewhatpromotionsreallydo/Promoperformance) |
| **Airlines & data platforms** (BUAN 6335 project) | A data platform for an airline merger, then tested on the real Alaska + Hawaiian merger: networks, on-time definitions, the worst day of 2024, delay chains, a flight-key test, and a bronze-silver-gold lakehouse | BTS on-time data 2024 (324,349 flights, real) | Python, PySpark, SQL, built for Microsoft Fabric |
| **Fleet safety & big data** (BUAN 6346 project) | A Hadoop risk pipeline, a Bayesian second opinion, driver vs. truck, risk profiles, a risk map | Course project data (driver names removed) | Hadoop (HDFS, Hive, Pig, Impala), Python, Power BI |

## How it's built

A static site: plain HTML, CSS and JavaScript, with no framework and no build step. The charts are drawn by a
small SVG chart kit (`scripts/viz.js`) from the data files in `data/`, which the scripts in `analysis/`
generate from the public sources.

| Path | What it is |
|---|---|
| `index.html` | All page content: home, the four capsules, toolkit, about, contact |
| `styles/main.css` | Design tokens (light and dark themes), layout, components |
| `scripts/app.js` | Router, theme, chapter navigation, toolkit, code tabs |
| `scripts/viz.js` | Chart kit: lines, bars, columns, sparklines, tooltips |
| `scripts/case-*.js` | One script per capsule (and per newer chapter) |
| `data/*.js` | Generated data (`window.DATA_*`). Re-run the scripts rather than editing by hand |
| `analysis/` | Data pipelines in Python and R, plus schema notes for the generated files |
| `fabric/` | The airline lakehouse: PySpark notebooks for Microsoft Fabric, SQL queries, run guide, local test tools |
| `reports/` | The attrition study as an R Markdown report |
| `downloads/` | Files offered on the site: the Excel Solver model, the Tableau data file, the lakehouse notebooks |

To view it locally:

    python -m http.server 8080      # then open http://localhost:8080

## Rebuilding the data

| Script | Input (download) | Output |
|---|---|---|
| `people_services.py` | [UCI #498 incident event log](https://archive.ics.uci.edu/dataset/498) (CC BY 4.0) | `data/people_services.js` |
| `store_ops.py` | `products.rda`, `transactions.rds`, `promotions.rds` from [completejourney](https://github.com/bradleyboehmke/completejourney/tree/master/data) (84.51° *The Complete Journey*); needs `pyreadr` | `data/store_ops.js` |
| `acquisition_integration.py` | [IBM HR attrition sample](https://github.com/IBM/employee-attrition-aif360/blob/master/data/emp_attrition.csv) | `data/integration.js` |
| `fleet_risk.py` | The BUAN 6346 course project files (not included); needs scikit-learn and SciPy | `data/fleet.js` |
| `people_attrition.R` (+ `.Rmd`) | IBM HR attrition sample; R 4.5 with dplyr, survival, broom, rpart, jsonlite, rmarkdown | `data/attrition.js`, `reports/people_attrition.html` |
| `airline_bts.py` | [BTS Reporting Carrier On-Time Performance](https://www.transtats.bts.gov/) 2024 (12 monthly zips) + [OurAirports](https://ourairports.com/data/) | `data/airline_real.js` |
| `geo_basemaps.py` | world-atlas / us-atlas TopoJSON (Natural Earth) + fleet city list | `data/geo.js` |
| `retail_promo_basket.py` | completejourney files (as above) | `data/retail_extra.js`, `downloads/tableau/` |
| `build_solver_workbook.py` | `data/retail_extra.js` order plan | `downloads/promo_order_optimizer.xlsx` |
| `fabric/tools/run_local.py` + `export_results.py` | BTS 2024 zips + OurAirports, through the three lakehouse notebooks on PySpark 3.5 | `data/fabric_lakehouse.js` |

Each script's docstring gives its exact command line. `analysis/*_SCHEMA.md` describe the generated files.

## Labels used on the page

- **Real**: public data, used as published.
- **Simulated**: modelled on top of real data where no public data exists (shelf stock, case packs, stock-record errors), with fixed random seeds.
- **Synthetic**: generated to mirror a confidential file (an acquired company's HR extract).

Employer data from ALTEN and Intermarché is confidential, so those capsules use public data with the same
shape to show the same work. The airline and fleet capsules use my course projects; company names and
figures in the airline design case are fictional, and driver names are left out of the fleet data.

## Data sources

UCI Machine Learning Repository #498 (CC BY 4.0) · 84.51° *The Complete Journey* via the `completejourney`
package · IBM HR attrition sample · US Bureau of Transportation Statistics on-time data (public domain) ·
OurAirports (public domain) · Natural Earth via world-atlas and us-atlas.
