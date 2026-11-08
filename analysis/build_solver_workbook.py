"""
Build downloads/promo_order_optimizer.xlsx: the promo-week order plan as an Excel Solver model.

A section manager has one mailer week coming, 12 promoted SKUs, a fixed order budget and a
fixed amount of shelf + backroom space. How many cases of each should she order?

  decision   x_i = cases ordered (whole numbers),  s_i = units sold
  maximise   sum_i  margin_i * s_i  -  leftover_cost_i * (pack_i * x_i - s_i)
  subject to s_i <= forecast_i              (can't sell more than demand)
             s_i <= pack_i * x_i            (can't sell more than you ordered)
             x_i >= supplier minimum_i
             sum_i unit_cost_i * pack_i * x_i <= budget
             sum_i ft3_per_case_i * x_i       <= space
             x_i integer, x, s >= 0

REAL (from data/retail_extra.js -> order_plan, built by retail_promo_basket.py from 84.51°
The Complete Journey): SKUs, the week's baseline, each SKU's promo lift, regular and promo prices.
ASSUMED (orange cells): unit cost %, vendor funding, case packs, supplier minimums, space per
unit, leftover cost %, budget, space.

The workbook carries:
  Instructions  how to run Solver (and the manual set-up, if the saved model doesn't load)
  Inputs        data + assumptions, colour coded; derived columns are formulas
  Model         decision cells (yellow), formulas, constraints, objective; opens on a
                rule-of-thumb plan (same-% cut, then top up the biggest gaps) so Solver has something to beat
  Answer        the optimum solved in Python (scipy HiGHS MILP), visible before Solver runs
and the Solver model itself as hidden sheet-level defined names on 'Model' (solver_opt,
solver_adj, solver_lhs1..6, ...), the way Excel saves a Solver model, so Data > Solver opens
pre-filled.

Checks (no Excel needed): every formula in the workbook is evaluated with a small Excel-formula
interpreter below; the inputs it computes are re-solved with scipy and must match the analysis
answer, and the Model's objective/constraints evaluated at that answer must match too.

Usage : python build_solver_workbook.py <site root> [extra sys.path entry for openpyxl]
"""
import json
import math
import os
import re
import sys

if len(sys.argv) > 2:
    sys.path.insert(0, sys.argv[2])
import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.defined_name import DefinedName
from scipy.optimize import Bounds, LinearConstraint, milp

SITE = sys.argv[1].rstrip("/\\")
SRC = os.path.join(SITE, "data", "retail_extra.js")
OUT = os.path.join(SITE, "downloads", "promo_order_optimizer.xlsx")

txt = open(SRC, encoding="utf-8").read()
data = json.loads(txt[txt.index("=") + 1:].strip().rstrip(";"))
plan = data["order_plan"]
K = plan["skus"]
A = plan["assumptions"]
n = len(K)

# ------------------------------------------------------------------ styles
NAVY = "1F3A5F"
F_REAL = PatternFill("solid", fgColor="DDEBF7")      # real data
F_ASSUME = PatternFill("solid", fgColor="FCE4D6")    # assumption: change me
F_DEC = PatternFill("solid", fgColor="FFF2CC")       # Solver decision cell
F_OBJ = PatternFill("solid", fgColor="E2EFDA")       # objective
F_HEAD = PatternFill("solid", fgColor=NAVY)
WHITE_B = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=14, color=NAVY)
NOTE = Font(italic=True, color="595959")
thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
thick = Side(style="medium", color="7F6000")
DEC_BOX = Border(left=thick, right=thick, top=thick, bottom=thick)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
USD, USD0, PCT, INT, DEC1, DEC2 = '"$"#,##0.00', '"$"#,##0', "0%", "#,##0", "0.0", "0.00"

wb = Workbook()
ws_i = wb.active
ws_i.title = "Instructions"
ws_in = wb.create_sheet("Inputs")
ws_m = wb.create_sheet("Model")
ws_a = wb.create_sheet("Answer")


def put(ws, ref, value, fmt=None, fill=None, font=None, border=BOX, align=None):
    c = ws[ref]
    c.value = value
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if font:
        c.font = font
    if border:
        c.border = border
    if align:
        c.alignment = align
    return c


def header(ws, row, cols, labels, height=45):
    for col, lab in zip(cols, labels):
        put(ws, f"{col}{row}", lab, fill=F_HEAD, font=WHITE_B, align=CENTER)
    ws.row_dimensions[row].height = height


# ================================================================== INPUTS
ws = ws_in
ws["A1"] = "Promo order optimizer · Inputs"
ws["A1"].font = TITLE
ws["A2"] = (f"Mailer week {plan['week']} (week starting {plan['week_start']}), 12 promoted SKUs. "
            "Source: 84.51° The Complete Journey (2,469 households, 2017).")
ws["A2"].font = NOTE
put(ws, "B3", "Real data", fill=F_REAL)
put(ws, "C3", "Assumption (change me)", fill=F_ASSUME)
put(ws, "D3", "Formula", border=BOX)
ws["E3"] = "Units = the panel's units; raise 'Store scale' to size the plan for a bigger store."
ws["E3"].font = NOTE

put(ws, "B5", "Global assumptions", font=BOLD, border=None)
glob = [
    ("Unit cost as % of the regular shelf price", A["cost_pct_of_regular"], PCT),
    ("Share of the promo discount funded by the supplier", A["vendor_funding_of_discount"], PCT),
    ("Order budget for this promotion (open-to-buy), $", plan["budget"], USD0),
    ("Shelf + backroom space for this promotion, ft³", plan["space"], INT),
    ("Store scale (multiplies forecast demand)", A["store_scale"], DEC2),
    ("Leftover cost, ambient (% of unit cost)", A["leftover_cost_pct"]["Ambient"], PCT),
    ("Leftover cost, chilled (% of unit cost)", A["leftover_cost_pct"]["Chilled"], PCT),
    ("Leftover cost, frozen (% of unit cost)", A["leftover_cost_pct"]["Frozen"], PCT),
]
G = {}
for k, (lab, val, fmt) in enumerate(glob):
    row = 6 + k
    put(ws, f"B{row}", lab)
    put(ws, f"C{row}", val, fmt=fmt, fill=F_ASSUME)
    G[lab] = f"$C${row}"
C_COST, C_FUND, C_BUDGET, C_SPACE, C_SCALE = "$C$6", "$C$7", "$C$8", "$C$9", "$C$10"
C_LEFT = {"Ambient": "$C$11", "Chilled": "$C$12", "Frozen": "$C$13"}
put(ws, "D6", "Why: a typical grocery gross margin on regular price is ~30%.", border=None, font=NOTE)
put(ws, "D7", "Why: suppliers usually pay part of a mailer discount (scan-back / deal allowance).", border=None, font=NOTE)
put(ws, "D8", f"Set to {A['budget_rule']}.", border=None, font=NOTE)
put(ws, "D9", f"Set to {A['space_rule']}.", border=None, font=NOTE)
put(ws, "D11", "Leftovers carry holding cost plus markdown/waste risk: higher for chilled.", border=None, font=NOTE)

R0 = 16                                            # first SKU row
put(ws, f"B{R0 - 2}", "Promoted SKUs", font=BOLD, border=None)
cols = list("ABCDEFGHIJKLMNOPQRST")
labels = ["#", "SKU id", "Product", "Category", "Storage", "Baseline units that week", "Promo lift (x baseline)",
          "Forecast demand, units", "Actual units sold that week", "Regular shelf price", "Promo price",
          "Discount depth", "Unit cost", "Margin per unit sold", "Leftover cost %", "Leftover cost per unit",
          "Case pack, units", "Supplier minimum, cases", "ft³ per unit", "ft³ per case"]
header(ws, R0 - 1, cols, labels, height=48)
for k, s in enumerate(K):
    r_ = R0 + k
    put(ws, f"A{r_}", k + 1, align=CENTER)
    put(ws, f"B{r_}", s["id"], fill=F_REAL)
    put(ws, f"C{r_}", f"{s['name']} ({s['supplier']})", fill=F_REAL)
    put(ws, f"D{r_}", s["cat"], fill=F_REAL)
    put(ws, f"E{r_}", s["zone"], fill=F_REAL)
    put(ws, f"F{r_}", s["base"], fmt=DEC1, fill=F_REAL)
    put(ws, f"G{r_}", s["lift"], fmt=DEC2, fill=F_REAL)
    put(ws, f"H{r_}", f"=ROUND(F{r_}*G{r_}*{C_SCALE},0)", fmt=INT)
    put(ws, f"I{r_}", s["actual"], fmt=INT, fill=F_REAL)
    put(ws, f"J{r_}", s["reg_price"], fmt=USD, fill=F_REAL)
    put(ws, f"K{r_}", s["promo_price"], fmt=USD, fill=F_REAL)
    put(ws, f"L{r_}", f"=1-K{r_}/J{r_}", fmt=PCT)
    put(ws, f"M{r_}", f"={C_COST}*J{r_}-{C_FUND}*(J{r_}-K{r_})", fmt=USD)
    put(ws, f"N{r_}", f"=K{r_}-M{r_}", fmt=USD)
    put(ws, f"O{r_}", f"={C_LEFT[s['zone']]}", fmt=PCT)
    put(ws, f"P{r_}", f"=M{r_}*O{r_}", fmt=USD)
    put(ws, f"Q{r_}", s["pack"], fmt=INT, fill=F_ASSUME)
    put(ws, f"R{r_}", s["min_cases"], fmt=INT, fill=F_ASSUME)
    put(ws, f"S{r_}", s["ft3_unit"], fmt=DEC2, fill=F_ASSUME)
    put(ws, f"T{r_}", f"=Q{r_}*S{r_}", fmt=DEC2)
R1 = R0 + n - 1
notes = [
    "Baseline: the SKU's average units in its ordinary weeks around this week (no promotion, not just after one).",
    "Promo lift: units / baseline in the SKU's OTHER mailer weeks of the year, so this week's result isn't used to forecast itself.",
    "Actual units sold that week is shown only to compare with the forecast; the model never uses it.",
    "Prices: regular = average shelf price in ordinary weeks; promo = what shoppers actually paid this week (loyalty price).",
    "Unit cost = cost% x regular price - supplier funding x (regular - promo). Margin per unit = promo price - unit cost.",
    f"Case pack: {A['pack_rule']}. Supplier minimum: {A['min_rule']}. Space per unit: rough category averages.",
]
for k, t in enumerate(notes):
    c = ws.cell(row=R1 + 2 + k, column=2, value=t)
    c.font = NOTE
for col, w in zip(cols, [4, 10, 52, 14, 10, 11, 10, 11, 11, 10, 10, 10, 10, 11, 10, 11, 9, 10, 9, 9]):
    ws.column_dimensions[col].width = w
ws.column_dimensions["B"].width = 46
ws.freeze_panes = f"D{R0}"

# ================================================================== MODEL
ws = ws_m
ws["A1"] = "Promo order optimizer · Model"
ws["A1"].font = TITLE
ws["A2"] = ("Yellow cells are what Solver changes. It opens on a rule-of-thumb plan (cut every SKU by the same %, then top up the biggest gaps); "
            "run Data > Solver (Simplex LP) to find the best plan.")
ws["A2"].font = NOTE
M0 = 5
mcols = list("ABCDEFGHIJKLMNO")
mlabels = ["#", "Product", "Forecast demand, units", "Case pack", "Supplier minimum, cases", "CASES TO ORDER",
           "Units ordered", "UNITS SOLD", "Leftover units", "Margin per unit sold", "Leftover cost per unit",
           "Purchase cost", "Space used, ft³", "Contribution (margin - leftover cost)", "Lost sales, units"]
header(ws, M0 - 1, mcols, mlabels, height=48)
nv = {s["id"]: (s["naive_cases"], s["naive_sold"]) for s in K}
for k, s in enumerate(K):
    r_, ri = M0 + k, R0 + k
    put(ws, f"A{r_}", k + 1, align=CENTER)
    put(ws, f"B{r_}", f"=Inputs!C{ri}")
    put(ws, f"C{r_}", f"=Inputs!H{ri}", fmt=INT)
    put(ws, f"D{r_}", f"=Inputs!Q{ri}", fmt=INT)
    put(ws, f"E{r_}", f"=Inputs!R{ri}", fmt=INT)
    put(ws, f"F{r_}", nv[s["id"]][0], fmt=INT, fill=F_DEC, border=DEC_BOX, font=BOLD)
    put(ws, f"G{r_}", f"=F{r_}*D{r_}", fmt=INT)
    put(ws, f"H{r_}", nv[s["id"]][1], fmt=INT, fill=F_DEC, border=DEC_BOX, font=BOLD)
    put(ws, f"I{r_}", f"=G{r_}-H{r_}", fmt=INT)
    put(ws, f"J{r_}", f"=Inputs!N{ri}", fmt=USD)
    put(ws, f"K{r_}", f"=Inputs!P{ri}", fmt=USD)
    put(ws, f"L{r_}", f"=G{r_}*Inputs!M{ri}", fmt=USD)
    put(ws, f"M{r_}", f"=F{r_}*Inputs!T{ri}", fmt=DEC1)
    put(ws, f"N{r_}", f"=J{r_}*H{r_}-K{r_}*I{r_}", fmt=USD)
    put(ws, f"O{r_}", f"=C{r_}-H{r_}", fmt=INT)
M1 = M0 + n - 1
MT = M1 + 1
put(ws, f"B{MT}", "Total", font=BOLD)
for col, fmt in [("C", INT), ("G", INT), ("H", INT), ("I", INT), ("L", USD), ("M", DEC1), ("N", USD), ("O", INT)]:
    put(ws, f"{col}{MT}", f"=SUM({col}{M0}:{col}{M1})", fmt=fmt, font=BOLD)

RC = MT + 2
put(ws, f"B{RC}", "Constraints", font=BOLD, border=None)
header(ws, RC + 1, list("BCDEF"), ["Constraint", "Left side", "", "Limit", "Status"], height=20)
put(ws, f"B{RC + 2}", "Total purchase cost <= order budget")
put(ws, f"C{RC + 2}", f"=L{MT}", fmt=USD)
put(ws, f"D{RC + 2}", "<=", align=CENTER)
put(ws, f"E{RC + 2}", f"=Inputs!{C_BUDGET}", fmt=USD)
put(ws, f"F{RC + 2}", f'=IF(C{RC + 2}<=E{RC + 2}+0.005,"OK","Over budget")')
put(ws, f"B{RC + 3}", "Total space used <= space available, ft³")
put(ws, f"C{RC + 3}", f"=M{MT}", fmt=DEC1)
put(ws, f"D{RC + 3}", "<=", align=CENTER)
put(ws, f"E{RC + 3}", f"=Inputs!{C_SPACE}", fmt=DEC1)
put(ws, f"F{RC + 3}", f'=IF(C{RC + 3}<=E{RC + 3}+0.005,"OK","Over space")')
per_sku = [
    (f"Units sold <= forecast demand (each SKU): H{M0}:H{M1} <= C{M0}:C{M1}", f"=SUMPRODUCT(--(H{M0}:H{M1}>C{M0}:C{M1}+0.0001))"),
    (f"Units sold <= units ordered (each SKU): H{M0}:H{M1} <= G{M0}:G{M1}", f"=SUMPRODUCT(--(H{M0}:H{M1}>G{M0}:G{M1}+0.0001))"),
    (f"Cases >= supplier minimum (each SKU): F{M0}:F{M1} >= E{M0}:E{M1}", f"=SUMPRODUCT(--(F{M0}:F{M1}<E{M0}:E{M1}-0.0001))"),
    (f"Cases are whole numbers: F{M0}:F{M1} = integer", f"=SUMPRODUCT(--(ABS(F{M0}:F{M1}-ROUND(F{M0}:F{M1},0))>0.0001))"),
]
for k, (lab, f_) in enumerate(per_sku):
    r_ = RC + 4 + k
    put(ws, f"B{r_}", lab)
    put(ws, f"C{r_}", f_, fmt=INT)
    put(ws, f"D{r_}", "rows broken", align=CENTER)
    put(ws, f"E{r_}", 0, fmt=INT)
    put(ws, f"F{r_}", f'=IF(C{r_}=0,"OK","Check")')
RO = RC + 9
put(ws, f"B{RO}", "OBJECTIVE: total contribution (maximise)", font=BOLD, fill=F_OBJ)
put(ws, f"C{RO}", f"=N{MT}", fmt=USD, font=Font(bold=True, size=12), fill=F_OBJ)
put(ws, f"B{RO + 1}", "Python optimum for comparison (Answer sheet)")
put(ws, f"C{RO + 1}", plan["result"]["objective"], fmt=USD)
put(ws, f"B{RO + 2}", "Gap to the optimum")
put(ws, f"C{RO + 2}", f"=C{RO}-C{RO + 1}", fmt=USD)
put(ws, f"B{RO + 3}", "Fill rate (units sold / forecast demand)")
put(ws, f"C{RO + 3}", f"=H{MT}/C{MT}", fmt=PCT)
for col, w in zip(mcols, [4, 50, 11, 8, 10, 11, 10, 11, 10, 10, 10, 11, 10, 14, 10]):
    ws.column_dimensions[col].width = w
ws.freeze_panes = f"C{M0}"

OBJ = f"$C${RO}"
ADJ = f"Model!$F${M0}:$F${M1},Model!$H${M0}:$H${M1}"
CONS = [  # (lhs, rel, rhs)   rel: 1 <=, 2 =, 3 >=, 4 int, 5 bin
    (f"Model!$H${M0}:$H${M1}", 1, f"Model!$C${M0}:$C${M1}"),
    (f"Model!$H${M0}:$H${M1}", 1, f"Model!$G${M0}:$G${M1}"),
    (f"Model!$F${M0}:$F${M1}", 3, f"Model!$E${M0}:$E${M1}"),
    (f"Model!$F${M0}:$F${M1}", 4, '"integer"'),
    (f"Model!$C${RC + 2}", 1, f"Model!$E${RC + 2}"),
    (f"Model!$C${RC + 3}", 1, f"Model!$E${RC + 3}"),
]

# ================================================================== INSTRUCTIONS
ws = ws_i
lines = [
    ("Promo order optimizer (Excel Solver)", TITLE),
    ("", None),
    ("The question", BOLD),
    (f"A mailer promotion starts in week {plan['week']}. The section manager must order 12 promoted SKUs with a fixed budget "
     "and limited shelf + backroom space. Ordering every SKU in full is not possible; the usual rule of thumb is to cut every SKU by the same % "
     "and top up the biggest gaps. Which mix of cases earns the most margin?", None),
    ("", None),
    ("What is real and what is assumed", BOLD),
    ("Real (blue): SKUs, each SKU's baseline that week, its measured promo lift from its other mailer weeks, regular and promo prices "
     "(84.51° The Complete Journey, 2,469 households, 2017).", None),
    ("Assumed (orange): unit cost %, supplier funding of the discount, case packs, supplier minimums, space per unit, leftover cost %, "
     "budget and space. Change any orange cell and re-run Solver.", None),
    ("", None),
    ("The model (a linear program with whole-number cases)", BOLD),
    ("Decision cells: Model!F (cases to order) and Model!H (units sold).", None),
    ("Objective: maximise total contribution = margin x units sold - leftover cost x leftover units (Model!" + OBJ.replace("$", "") + ").", None),
    ("Constraints: units sold <= forecast demand; units sold <= units ordered; cases >= supplier minimum; cases are whole numbers; "
     "total purchase cost <= budget; total space <= space available.", None),
    ("", None),
    ("How to run it", BOLD),
    ("1. Turn on Solver once: File > Options > Add-ins > Manage: Excel Add-ins > Go > tick 'Solver Add-in' > OK.", None),
    ("2. Click the Model tab. Solver reads the model saved on the sheet that is active.", None),
    ("3. Data > Solver. The dialog should open filled in (the model is saved in the workbook). Check it matches the table below.", None),
    ("4. Options > All Methods: set Integer Optimality (%) to 0, so Solver doesn't stop at a 'good enough' whole-number plan.", None),
    ("5. Click Solve, choose 'Keep Solver Solution'. Model!" + OBJ.replace("$", "") + " should match the Answer sheet "
     f"(${plan['result']['objective']:,.2f}); the gap cell below it should show $0.00.", None),
    ("", None),
    ("If the dialog opens empty, enter this by hand", BOLD),
]
r_ = 1
for t, f_ in lines:
    c = ws.cell(row=r_, column=1, value=t)
    if f_:
        c.font = f_
    c.alignment = WRAP
    r_ += 1
setup = [("Set Objective", OBJ), ("To", "Max"),
         ("By Changing Variable Cells", ADJ.replace("Model!", "")),
         ("Subject to the Constraints", f"$H${M0}:$H${M1} <= $C${M0}:$C${M1}"),
         ("", f"$H${M0}:$H${M1} <= $G${M0}:$G${M1}"),
         ("", f"$F${M0}:$F${M1} >= $E${M0}:$E${M1}"),
         ("", f"$F${M0}:$F${M1} = integer"),
         ("", f"$C${RC + 2} <= $E${RC + 2}   (budget)"),
         ("", f"$C${RC + 3} <= $E${RC + 3}   (space)"),
         ("Make Unconstrained Variables Non-Negative", "ticked"),
         ("Select a Solving Method", "Simplex LP")]
for a_, b_ in setup:
    put(ws, f"A{r_}", a_, font=BOLD, border=None)
    put(ws, f"B{r_}", b_, border=None)
    r_ += 1
r_ += 1
more = [
    ("Things to try", BOLD),
    ("Raise the budget (Inputs!C8) or the space (Inputs!C9) and re-solve: which constraint was holding the plan back?", None),
    ("Set supplier funding (Inputs!C7) to 0%: margins on deep discounts shrink or go negative, and the plan shifts to the SKUs that still pay.", None),
    ("Limits: if a margin turns negative the model simply 'sells' none of that SKU, so keep margins positive. "
     "Demand is a point forecast; a real plan would add safety stock for forecast error.", None),
    ("", None),
    ("Sheets: Inputs (data + assumptions) · Model (Solver model) · Answer (optimum solved in Python with scipy/HiGHS, for checking).", NOTE),
    ("Built by analysis/build_solver_workbook.py from data/retail_extra.js (analysis/retail_promo_basket.py).", NOTE),
]
for t, f_ in more:
    c = ws.cell(row=r_, column=1, value=t)
    if f_:
        c.font = f_
    c.alignment = WRAP
    r_ += 1
ws.column_dimensions["A"].width = 44
ws.column_dimensions["B"].width = 70
for row in ws.iter_rows(min_row=1, max_row=r_):
    for c in row:
        if c.column == 1 and isinstance(c.value, str) and len(c.value) > 60:
            ws.merge_cells(start_row=c.row, start_column=1, end_row=c.row, end_column=2)
            ws.row_dimensions[c.row].height = 15 * math.ceil(len(c.value) / 105)

# ================================================================== ANSWER (static values from Python)
ws = ws_a
res = plan["result"]
ws["A1"] = "Promo order optimizer · Answer (solved in Python)"
ws["A1"].font = TITLE
ws["A2"] = ("Optimal whole-number plan from scipy.optimize.milp (HiGHS), same inputs and constraints as the Model sheet. "
            "Excel Solver (Simplex LP, integer optimality 0%) should reach the same objective.")
ws["A2"].font = NOTE
acols = list("ABCDEFGHIJKL")
header(ws, 4, acols, ["#", "Product", "Forecast demand", "Cases to order", "Units ordered", "Units sold", "Leftover units",
                      "Lost sales", "Contribution", "Rule of thumb: cases", "Rule of thumb: units sold", "Rule of thumb: contribution"])
for k, s in enumerate(K):
    r_ = 5 + k
    contrib = s["margin"] * s["opt_sold"] - s["hold"] * s["opt_left"]
    nv_left = s["naive_cases"] * s["pack"] - s["naive_sold"]
    contrib_nv = s["margin"] * s["naive_sold"] - s["hold"] * nv_left
    vals = [k + 1, f"{s['name']} ({s['supplier']})", s["forecast"], s["opt_cases"], s["opt_cases"] * s["pack"], s["opt_sold"],
            s["opt_left"], s["forecast"] - s["opt_sold"], contrib, s["naive_cases"], s["naive_sold"], contrib_nv]
    for col, v_, fmt in zip(acols, vals, [None, None, INT, INT, INT, INT, INT, INT, USD, INT, INT, USD]):
        put(ws, f"{col}{r_}", v_, fmt=fmt, fill=F_DEC if col == "D" else None)
rt = 5 + n
put(ws, f"B{rt}", "Total", font=BOLD)
for col, fmt in [("C", INT), ("E", INT), ("F", INT), ("G", INT), ("H", INT), ("I", USD), ("K", INT), ("L", USD)]:
    put(ws, f"{col}{rt}", f"=SUM({col}5:{col}{rt - 1})", fmt=fmt, font=BOLD)
summ = [
    ("Optimal contribution (objective)", res["objective"], USD),
    ("Rule-of-thumb plan (same-% cut, then top up)", res["naive_objective"], USD),
    ("Gain from optimising (same budget, same space)", res["uplift_vs_naive"], USD),
    ("Budget used / available", f"${res['budget_used']:,.2f} / ${plan['budget']:,.0f}", None),
    ("Space used / available, ft³", f"{res['space_used']:.1f} / {plan['space']:.0f}", None),
    ("Fill rate: optimal plan", res["fill_rate"], PCT),
    ("Fill rate: rule of thumb", res["naive_fill_rate"], PCT),
    ("LP relaxation (fractional cases allowed): upper bound", res["lp_relaxation"], USD),
]
r_ = rt + 2
for lab, v_, fmt in summ:
    put(ws, f"B{r_}", lab, font=BOLD)
    put(ws, f"C{r_}", v_, fmt=fmt)
    r_ += 1
fill_ = sorted(K, key=lambda s: s["opt_sold"] / s["forecast"])
worst = fill_[0]
binding = [nm for nm, used, cap in [("budget", res["budget_used"], plan["budget"]), ("space", res["space_used"], plan["space"])]
           if cap - used < 0.02 * cap]
put(ws, f"B{r_ + 1}", f"Reading it: {' and '.join(binding) or 'no constraint'} {'are' if len(binding) > 1 else 'is'} binding, so every case has to "
    f"earn its place. The plan cuts hardest where margin per $ and per ft³ is thinnest: {worst['cat'].lower()} "
    f"({worst['name'].split(' · ')[0]}, {worst['depth']:.0%} off) gets {worst['opt_sold']} of {worst['forecast']} forecast units.",
    border=None, font=NOTE)
for col, w in zip(acols, [4, 52, 10, 10, 10, 10, 10, 10, 12, 11, 11, 12]):
    ws.column_dimensions[col].width = w

# ================================================================== SOLVER MODEL (hidden sheet-level names on 'Model')
solver = {
    "solver_adj": ADJ, "solver_opt": f"Model!{OBJ}", "solver_typ": "1", "solver_val": "0",
    "solver_eng": "2", "solver_lin": "1", "solver_neg": "1", "solver_num": str(len(CONS)),
    "solver_cvg": "0.0001", "solver_drv": "1", "solver_est": "1", "solver_itr": "2147483647",
    "solver_mip": "2147483647", "solver_mni": "30", "solver_mrt": "0.075", "solver_msl": "2",
    "solver_nod": "2147483647", "solver_nwt": "1", "solver_pre": "0.000001", "solver_rbv": "1",
    "solver_rlx": "2", "solver_rsd": "0", "solver_scl": "1", "solver_sho": "2", "solver_ssz": "100",
    "solver_tim": "2147483647", "solver_tol": "0", "solver_ver": "3",
}
for k, (lhs, rel, rhs) in enumerate(CONS, 1):
    solver[f"solver_lhs{k}"] = lhs
    solver[f"solver_rel{k}"] = str(rel)
    solver[f"solver_rhs{k}"] = rhs
for name, ref in sorted(solver.items()):
    ws_m.defined_names[name] = DefinedName(name, attr_text=ref, hidden=True)

wb.active = 0
wb.calculation.fullCalcOnLoad = True
os.makedirs(os.path.dirname(OUT), exist_ok=True)
wb.save(OUT)
print("saved", OUT, os.path.getsize(OUT), "bytes")


# ================================================================== VERIFY (no Excel needed)
class Book:
    """Tiny Excel formula evaluator for the functions this workbook uses."""
    TOK = re.compile(r"\s*(?:(?P<num>\d+\.\d*(?:[eE][-+]?\d+)?|\d+(?:[eE][-+]?\d+)?|\.\d+)|(?P<str>\"[^\"]*\")"
                     r"|(?P<ref>(?:[A-Za-z_][\w\.]*!)?\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)"
                     r"|(?P<fn>[A-Z][A-Z0-9\.]*)\(|(?P<op><=|>=|<>|--|[-+*/^=<>(),&]))")

    def __init__(self, wb, override=None):
        self.wb, self.cache, self.override = wb, {}, override or {}

    def cell(self, sheet, ref):
        key = (sheet, ref.replace("$", ""))
        if key in self.override:
            return self.override[key]
        if key not in self.cache:
            v = self.wb[sheet][key[1]].value
            if isinstance(v, str) and v.startswith("="):
                self.cache[key] = None
                v = self.formula(sheet, v[1:])
            self.cache[key] = v
        return self.cache[key]

    def rng(self, sheet, ref):
        from openpyxl.utils import range_boundaries, get_column_letter
        c1, r1, c2, r2 = range_boundaries(ref.replace("$", ""))
        return np.array([[self.cell(sheet, f"{get_column_letter(c)}{r}") for c in range(c1, c2 + 1)]
                         for r in range(r1, r2 + 1)], dtype=object).ravel()

    def formula(self, sheet, f):
        toks, pos = [], 0
        while pos < len(f):
            m = self.TOK.match(f, pos)
            if not m or m.end() == pos:
                if f[pos:].strip() == "":
                    break
                raise ValueError(f"cannot parse {f!r} at {pos}")
            toks.append((m.lastgroup, m.group(m.lastgroup)))
            pos = m.end()
        saved = getattr(self, "t", None), getattr(self, "i", None), getattr(self, "sheet", None)   # formulas nest
        self.t, self.i, self.sheet = toks, 0, sheet
        out = self.compare()
        assert self.i == len(self.t), f"trailing tokens in {f}"
        self.t, self.i, self.sheet = saved
        return out

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        self.i += 1
        return self.t[self.i - 1]

    def compare(self):
        a = self.add()
        k, v = self.peek()
        if k == "op" and v in ("=", "<>", "<=", ">=", "<", ">"):
            self.take()
            b = self.add()
            ops = {"=": np.equal, "<>": np.not_equal, "<=": np.less_equal, ">=": np.greater_equal, "<": np.less, ">": np.greater}
            a = ops[v](np.asarray(a, dtype=float) if not isinstance(a, str) else a, np.asarray(b, dtype=float) if not isinstance(b, str) else b)
        return a

    def add(self):
        a = self.mul()
        while self.peek() in (("op", "+"), ("op", "-")):
            _, v = self.take()
            b = self.mul()
            a = np.add(np.asarray(a, float), np.asarray(b, float)) if v == "+" else np.subtract(np.asarray(a, float), np.asarray(b, float))
        return a

    def mul(self):
        a = self.unary()
        while self.peek() in (("op", "*"), ("op", "/")):
            _, v = self.take()
            b = self.unary()
            a = np.multiply(np.asarray(a, float), np.asarray(b, float)) if v == "*" else np.divide(np.asarray(a, float), np.asarray(b, float))
        return a

    def unary(self):
        k, v = self.peek()
        if k == "op" and v in ("-", "--", "+"):
            self.take()
            x = np.asarray(self.unary(), dtype=float)
            return -x if v == "-" else x
        return self.primary()

    def primary(self):
        k, v = self.take()
        if k == "num":
            return float(v)
        if k == "str":
            return v[1:-1]
        if k == "ref":
            sheet, ref = (v.split("!") if "!" in v else (self.sheet, v))
            return self.rng(sheet, ref) if ":" in ref else self.cell(sheet, ref)
        if k == "op" and v == "(":
            x = self.compare()
            assert self.take() == ("op", ")")
            return x
        if k == "fn":
            args = []
            if self.peek() != ("op", ")"):
                args.append(self.compare())
                while self.peek() == ("op", ","):
                    self.take()
                    args.append(self.compare())
            assert self.take() == ("op", ")")
            return self.call(v, args)
        raise ValueError(f"unexpected token {k} {v}")

    @staticmethod
    def xround(x, d):
        x = np.asarray(x, dtype=float)
        q = 10.0 ** d
        return np.sign(x) * np.floor(np.abs(x) * q + 0.5 + 1e-9) / q

    def call(self, fn, a):
        if fn == "SUM":
            return float(sum(np.sum(np.asarray(x, dtype=float)) for x in a))
        if fn == "SUMPRODUCT":
            prod = np.ones_like(np.asarray(a[0], dtype=float))
            for x in a:
                prod = prod * np.asarray(x, dtype=float)
            return float(prod.sum())
        if fn == "ROUND":
            return self.xround(a[0], int(a[1]))
        if fn == "ABS":
            return np.abs(np.asarray(a[0], dtype=float))
        if fn == "IF":
            return a[1] if bool(a[0]) else a[2]
        raise ValueError(f"function {fn} not supported")


wb2 = load_workbook(OUT)
names = {nm: dn.attr_text for nm, dn in wb2["Model"].defined_names.items()}
assert set(names) == set(solver) and all(names[k] == v for k, v in solver.items()), "Solver names did not round-trip"
assert wb2.sheetnames == ["Instructions", "Inputs", "Model", "Answer"]
bk = Book(wb2)
# every formula in the workbook evaluates without error
n_f = 0
for ws in wb2.worksheets:
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                bk.cell(ws.title, c.coordinate)
                n_f += 1
print("formulas evaluated", n_f)
# inputs computed by the workbook -> independent scipy solve
ev = lambda col: np.array([float(bk.cell("Inputs", f"{col}{R0 + k}")) for k in range(n)])
F, pk, cst, mg, hd, sp, mn = ev("H"), ev("Q"), ev("M"), ev("N"), ev("P"), ev("T"), ev("R")
assert np.allclose(F, [s["forecast"] for s in K]) and np.allclose(mg, [s["margin"] for s in K], atol=1e-4)
B, S = float(bk.cell("Inputs", C_BUDGET)), float(bk.cell("Inputs", C_SPACE))
c = -np.concatenate([-hd * pk, mg + hd])
Am = np.zeros((n + 2, 2 * n))
Am[:n, :n], Am[:n, n:], Am[n, :n], Am[n + 1, :n] = -np.diag(pk), np.eye(n), cst * pk, sp
sol = milp(c, constraints=LinearConstraint(Am, -np.inf, np.r_[np.zeros(n), B, S]), integrality=np.r_[np.ones(n), np.zeros(n)],
           bounds=Bounds(np.r_[mn, np.zeros(n)], np.r_[np.full(n, np.inf), F]))
assert sol.success
x = np.round(sol.x[:n])
s_ = np.minimum(F, pk * x)
assert abs(-sol.fun - res["objective"]) < 0.01, (-sol.fun, res["objective"])
assert np.allclose(x, [s["opt_cases"] for s in K]), "re-solve picked a different plan"
# Model formulas at the optimum and at the opening (same-% cut) plan
for label_, xs, ss, target in [("optimum", x, s_, res["objective"]),
                               ("rule-of-thumb plan", [s["naive_cases"] for s in K], [s["naive_sold"] for s in K], res["naive_objective"])]:
    ov = {}
    for k in range(n):
        ov[("Model", f"F{M0 + k}")] = float(xs[k])
        ov[("Model", f"H{M0 + k}")] = float(ss[k])
    bm = Book(wb2, ov)
    obj = float(bm.cell("Model", OBJ))
    stat = [bm.cell("Model", f"F{RC + 2 + j}") for j in range(6)]
    print(f"Model at {label_}: objective {obj:.2f} (expected {target:.2f}) budget {float(bm.cell('Model', f'C{RC + 2}')):.2f}/{B:.0f} "
          f"space {float(bm.cell('Model', f'C{RC + 3}')):.2f}/{S:.0f} status {stat} gap {float(bm.cell('Model', f'C{RO + 2}')):.2f}")
    assert abs(obj - target) < 0.01 and all(s_ == "OK" for s_ in stat)
print("Solver names:", ", ".join(f"{k}={v}" for k, v in sorted(names.items()) if k in ("solver_opt", "solver_adj", "solver_eng", "solver_num", "solver_typ", "solver_neg", "solver_tol")))
print("OK: workbook formulas, constraints and objective agree with the scipy answer")
