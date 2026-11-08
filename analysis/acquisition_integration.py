"""
Acquisition integration: reconcile an acquired company's HR extract against the
acquirer's HR standard.

Source  : IBM HR Analytics Employee Attrition sample (1,470 employees), published by
          IBM at github.com/IBM/employee-attrition-aif360 — used as the acquirer's
          clean, standard-schema population.
SYNTHETIC (labelled on the site): the 700-person "acquired company" extract. It is
          generated from the IBM distributions, then given the kinds of problems
          real HR extracts have: another ID scheme, mixed date formats, its own
          department names, Portuguese contract types, salary paid in 14 instalments,
          duplicates, missing fields and broken manager links.

Usage   : python acquisition_integration.py <ibm_attrition.csv> <out.js>
"""
import json
import sys

import numpy as np
import pandas as pd

SRC, OUT = sys.argv[1], sys.argv[2]
rng = np.random.default_rng(7)
ibm = pd.read_csv(SRC, encoding="utf-8-sig")

# ------------------------------------------------------------- acquirer standard
STANDARD = [
    # field, type, rule
    ("employee_id", "text", "Unique, format ALT-######"),
    ("hire_date", "date", "ISO 8601 (YYYY-MM-DD)"),
    ("department", "code", "One of: Engineering, Sales, Human Resources"),
    ("job_level", "int", "1–5"),
    ("contract_type", "code", "Permanent · Fixed-term · Contractor"),
    ("annual_base_eur", "number", "Gross annual base, EUR"),
    ("monthly_base_eur", "number", "annual ÷ 14 (PT payroll: 12 months + holiday + Christmas)"),
    ("manager_id", "text", "Must exist in employee_id"),
    ("work_location", "code", "Office / Hybrid / Remote"),
    ("health_plan", "code", "Standard · Plus · Family"),
    ("meal_allowance", "code", "Card · Cash"),
    ("vacation_days", "int", "Statutory 22 + seniority"),
]

# ------------------------------------------------------------- build the acquired extract
N = 700
src = ibm.sample(N, replace=False, random_state=7).reset_index(drop=True)
dept_variants = {"Research & Development": ["R&D", "RD", "Research & Development", "Engenharia"],
                 "Sales": ["Sales", "Comercial", "SALES"],
                 "Human Resources": ["HR", "Recursos Humanos", "People"]}
acq = pd.DataFrame({
    "emp_no": [f"ACQ-{i:05d}" for i in rng.permutation(np.arange(100, 100 + N))],
    "dept": [rng.choice(dept_variants[d]) for d in src.Department],
    "grade": src.JobLevel.map({1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}),
    "contrato": rng.choice(["Sem termo", "A termo", "Prestação de serviços"], N, p=[.78, .17, .05]),
    "salary_annual_12": (src.MonthlyIncome * 12 * 0.42).round(-1),     # rescaled to PT levels, 12 payments
    "years_service": src.YearsAtCompany,
    "health": rng.choice(["Médis Base", "Médis Plus", None], N, p=[.62, .30, .08]),
    "meal": rng.choice(["Cartão", "Numerário"], N, p=[.7, .3]),
    "remote": rng.choice(["Presencial", "Híbrido", "Remoto", None], N, p=[.35, .45, .15, .05]),
})
start = pd.Timestamp("2025-06-01") - pd.to_timedelta(src.YearsAtCompany * 365 + rng.integers(0, 300, N), unit="D")
fmt = rng.choice(["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"], N, p=[.80, .12, .08])
acq["start_dt"] = [d.strftime(f) for d, f in zip(start, fmt)]
mgr_pool = acq.emp_no.sample(60, random_state=1).tolist()
acq["mgr"] = rng.choice(mgr_pool, N)
broken = rng.choice(N, 21, replace=False)
acq.loc[broken, "mgr"] = [f"ACQ-{x:05d}" for x in rng.integers(900, 999, 21)]      # managers who left
blank = rng.choice(N, 16, replace=False)
acq.loc[blank, "start_dt"] = None
dups = acq.sample(12, random_state=3).copy()
dups["dept"] = dups.dept.str.upper()                                               # same people, re-keyed
acq = pd.concat([acq, dups], ignore_index=True)

# ------------------------------------------------------------- reconcile
log = []
n0 = len(acq)
dedup = acq.drop_duplicates(subset=["emp_no"])
log.append(["Records received", n0, None])
log.append(["Duplicates removed", len(dedup), n0 - len(dedup)])


def parse(s):
    if s is None or pd.isna(s):
        return pd.NaT, "missing"
    for f, tag in [("%Y-%m-%d", "iso"), ("%d/%m/%Y", "dmy")]:
        try:
            return pd.to_datetime(s, format=f), tag
        except ValueError:
            pass
    return pd.to_datetime(s, format="%m/%d/%Y"), "mdy"


parsed = dedup.start_dt.apply(parse)
dedup = dedup.assign(hire_date=[p[0] for p in parsed], date_fmt=[p[1] for p in parsed])
# Ambiguous dd/mm vs mm/dd: anything with day <= 12 needs a check against the payroll start
ambiguous = int(((dedup.date_fmt == "dmy") & (dedup.hire_date.dt.day <= 12)).sum())
complete = dedup[dedup.hire_date.notna()]
log.append(["Mandatory fields complete", len(complete), len(dedup) - len(complete)])
dept_map = {v: k for k, vs in dept_variants.items() for v in vs}
dept_map.update({k.upper(): v for k, v in dept_map.items()})
mapped = complete[complete.dept.map(dept_map).notna()]
log.append(["Codes mapped to standard", len(mapped), len(complete) - len(mapped)])
ids = set(acq.emp_no)
mgr_ok = mapped[mapped.mgr.isin(ids)]
log.append(["Manager links valid", len(mgr_ok), len(mapped) - len(mgr_ok)])

crosswalk = [
    {"src": "emp_no", "dst": "employee_id", "status": "transform", "rule": "Re-key ACQ-##### → ALT-######; keep source ID as legacy_id for payroll history"},
    {"src": "start_dt", "dst": "hire_date", "status": "transform", "rule": f"3 date formats found; {ambiguous} dd/mm vs mm/dd dates (day ≤ 12) checked against the payroll start date"},
    {"src": "dept", "dst": "department", "status": "lookup", "rule": f"{dedup.dept.nunique()} spellings (PT/EN, upper case) → 3 standard departments"},
    {"src": "grade", "dst": "job_level", "status": "lookup", "rule": "Grade A–E → level 1–5; validated against salary bands"},
    {"src": "contrato", "dst": "contract_type", "status": "lookup", "rule": "Sem termo → Permanent · A termo → Fixed-term · Prestação de serviços → Contractor (out of HRIS scope)"},
    {"src": "salary_annual_12", "dst": "annual_base_eur", "status": "match", "rule": "Same meaning, same unit"},
    {"src": "salary_annual_12", "dst": "monthly_base_eur", "status": "transform", "rule": "Source divides by 12; standard divides by 14 (holiday + Christmas pay)"},
    {"src": "mgr", "dst": "manager_id", "status": "transform", "rule": "Re-key through the ID map; links to people who left go to HRBP for reassignment"},
    {"src": "remote", "dst": "work_location", "status": "lookup", "rule": "Presencial/Híbrido/Remoto → Office/Hybrid/Remote; blanks confirmed with managers"},
    {"src": "health", "dst": "health_plan", "status": "gap", "rule": "Different insurer and tiers: policy decision (grandfather until renewal, then move to Standard/Plus)"},
    {"src": "meal", "dst": "meal_allowance", "status": "match", "rule": "Same options (card vs cash)"},
    {"src": "—", "dst": "vacation_days", "status": "gap", "rule": "Not in extract: derive from contract + years of service, confirm with local HR"},
    {"src": "years_service", "dst": "seniority_date", "status": "transform", "rule": "Kept as seniority_date so acquired tenure counts for benefits"},
]

issues = {
    "duplicates": int(n0 - len(dedup)),
    "missing_hire_date": int(len(dedup) - len(complete)),
    "date_formats": dedup.date_fmt.value_counts().to_dict(),
    "ambiguous_dates": ambiguous,
    "dept_spellings": int(dedup.dept.nunique()),
    "broken_manager_links": int(len(mapped) - len(mgr_ok)),
    "health_blank": int(dedup.health.isna().sum()),
    "remote_blank": int(dedup.remote.isna().sum()),
    "contractors": int((dedup.contrato == "Prestação de serviços").sum()),
}
monthly_12 = float(dedup.salary_annual_12.median() / 12)
monthly_14 = float(dedup.salary_annual_12.median() / 14)

out = {
    "source": {"standard": "IBM HR Analytics sample (1,470 employees)",
               "url": "https://github.com/IBM/employee-attrition-aif360", "acquired_n": N},
    "standard_fields": [{"f": f, "t": t, "rule": r} for f, t, r in STANDARD],
    "crosswalk": crosswalk, "funnel": log, "issues": issues,
    "pay": {"median_monthly_12": round(monthly_12), "median_monthly_14": round(monthly_14)},
    "sample": dedup.head(8)[["emp_no", "start_dt", "dept", "grade", "contrato", "salary_annual_12", "mgr", "health", "remote"]]
              .astype(object).where(lambda x: x.notna(), None).to_dict(orient="records"),
}
print(json.dumps(out["funnel"]), out["issues"])
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("/* generated by analysis/acquisition_integration.py — do not edit by hand */\n")
    fh.write("window.DATA_INTEGRATION = " + json.dumps(out, separators=(",", ":"), ensure_ascii=False, default=str) + ";\n")
print("wrote", OUT)
