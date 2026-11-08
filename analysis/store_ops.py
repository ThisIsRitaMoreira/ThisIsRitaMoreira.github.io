"""
Store operations: priority products, inventory audit + cycle counts, order recommendations.

Source  : 84.51° "The Complete Journey" (via the `completejourney` R package):
          one year (2017) of grocery transactions from 2,469 households across
          the chain's stores, plus weekly in-store display and mailer promotions.
          https://github.com/bradleyboehmke/completejourney · https://www.8451.com/area51/
REAL    : products, sections, weekly units sold, prices, discounts, mailer/display weeks.
SIMULATED (clearly labelled on the site): on-hand stock, supplier case packs,
          record-error rates. Shelf stock isn't in any public dataset, so I
          simulate it from the real demand, with a fixed seed.

Usage   : python store_ops.py <dir with products.rda, transactions.rds, promotions.rds> <out.js> <pylib dir>
"""
import json
import sys

sys.path.insert(0, sys.argv[3])
import numpy as np
import pandas as pd
import pyreadr

SRC, OUT = sys.argv[1].rstrip("/\\"), sys.argv[2]
rng = np.random.default_rng(2024)
WEEKS = list(range(1, 53))           # week 53 is a single morning: drop it
AUDIT_STORE = "367"                  # the chain's largest store by SKU count
# non-merchandise departments (fuel, coupons, services) are not stock you can count
EXCLUDE_DEPTS = {"FUEL", "MISCELLANEOUS", "KIOSK-GAS", "POSTAL CENTER", "COUPON", "GM MERCH EXP",
                 "PHOTO", "VIDEO", "TRAVEL & LEISUR", "CNTRL/STORE SUP", "RX", "PHARMACY SUPPLY",
                 "CHARITABLE CONT", "VIDEO RENTAL", "POSTAL", "COUP/STR & MFG", "PHOTO & VIDEO"}

SECTIONS = {
    "Dairy": ["FLUID MILK PRODUCTS", "CHEESE", "YOGURT", "EGGS"],
    "Drinks": ["SOFT DRINKS", "WATER - CARBONATED/FLVRD DRINK", "REFRGRATD JUICES/DRNKS", "CANNED JUICES"],
    "Bakery": ["BAKED BREAD/BUNS/ROLLS", "BAKED SWEET GOODS", "BREAD"],
    "Frozen": ["FRZN MEAT/MEAT DINNERS", "FROZEN PIZZA", "ICE CREAM/MILK/SHERBTS"],
    "Meat & deli": ["BEEF", "CHICKEN", "PORK", "LUNCHMEAT", "DELI MEATS"],
    "Produce": ["TROPICAL FRUIT", "POTATOES", "VEGETABLES SALAD", "BERRIES", "APPLES", "SALAD MIX", "ONIONS", "TOMATOES"],
    "Pantry & snacks": ["BAG SNACKS", "COLD CEREAL", "SOUP", "CRACKERS/MISC BKD FD", "VEGETABLES - SHELF STABLE"],
}
PER_SECTION = 20

# ------------------------------------------------------------------ load
prod = pyreadr.read_r(f"{SRC}/products.rda")["products"]
tx = pyreadr.read_r(f"{SRC}/transactions.rds")[None]
tx = tx[tx.week.isin(WEEKS)].merge(prod, on="product_id", how="left")
tx = tx[~tx.department.isin(EXCLUDE_DEPTS) & tx.product_category.notna()
        & (tx.product_category != "COUPON/MISC ITEMS") & (tx.quantity > 0)]
print("lines", len(tx), "skus", tx.product_id.nunique())


def label(row):
    pt = str(row.product_type).title().replace("/", " / ") if pd.notna(row.product_type) else str(row.product_category).title()
    size = f" · {row.package_size}" if pd.notna(row.package_size) else ""
    own = " · Own brand" if row.brand == "Private" else ""
    return f"{pt}{size}{own}"


# ================================================================== 1. AUDIT (store 367)
s = tx[tx.store_id == AUDIT_STORE]
sku = s.groupby("product_id").agg(sales=("sales_value", "sum"), units=("quantity", "sum"),
                                   lines=("basket_id", "size")).join(prod.set_index("product_id"))
sku = sku.sort_values("sales", ascending=False)
sku["cum"] = sku.sales.cumsum() / sku.sales.sum()
sku["abc"] = np.where(sku.cum <= 0.80, "A", np.where(sku.cum <= 0.95, "B", "C"))
# Panel data covers ~2.5k households, so scale lines to a full store's traffic
# (x40, a typical panel-to-store ratio) before turning them into an error hazard.
weekly_moves = sku.lines * 40 / len(WEEKS)
# SIMULATED: chance per week that the stock record drifts from the shelf:
# grows with how often the item moves (scan errors, unrecorded waste, receiving).
K = 0.0045
sku["h"] = (1 - np.exp(-K * weekly_moves)).clip(lower=0.004)
print("audit SKUs", len(sku), sku.abc.value_counts().to_dict(),
      "baseline accuracy after 1y w/o counts", round(float(((1 - sku.h) ** 52).mean()), 3))

# hazard bins per class -> lets the browser compute accuracy for any count frequency
h_bins = {}
for c, g in sku.groupby("abc"):
    qs = pd.qcut(g.h.rank(method="first"), 8, labels=False)
    h_bins[c] = [[round(float(x.h.mean()), 5), int(len(x))] for _, x in g.groupby(qs)]
dept = sku.groupby(["department", "abc"]).agg(n=("sales", "size"), sales=("sales", "sum")).reset_index()
dept_tbl = {}
for _, x in dept.iterrows():
    dept_tbl.setdefault(x.department, {"A": 0, "B": 0, "C": 0, "sales": 0.0})
    dept_tbl[x.department][x.abc] = int(x.n)
    dept_tbl[x.department]["sales"] += float(x.sales)
dept_rows = sorted(({"d": k.title(), **v, "sales": round(v["sales"])} for k, v in dept_tbl.items()),
                   key=lambda r: -(r["A"] + r["B"] + r["C"]))
# SIMULATED audit result: did each SKU's record match the shelf at the wall-to-wall count?
miss = rng.random(len(sku)) > (1 - sku.h.values) ** 52
sku["miss"] = miss
audit_dept = sku.groupby("department").agg(n=("miss", "size"), miss=("miss", "sum")).sort_values("n", ascending=False)
audit = {
    "store": AUDIT_STORE, "skus": int(len(sku)),
    "abc": {c: {"n": int((sku.abc == c).sum()), "sales_share": round(float(sku.loc[sku.abc == c, "sales"].sum() / sku.sales.sum()), 3)} for c in "ABC"},
    "h_bins": h_bins, "dept": dept_rows[:12],
    "found": {"checked": int(len(sku)), "mismatch": int(miss.sum()),
              "by_dept": [{"d": i.title(), "n": int(x.n), "miss": int(x.miss)} for i, x in audit_dept.head(10).iterrows()]},
}

# ================================================================== 2. SECTION SKUs (chain level)
cat2sec = {c: sec for sec, cats in SECTIONS.items() for c in cats}
tx["section"] = tx.product_category.map(cat2sec)
sx = tx[tx.section.notna()]
wk = sx.groupby(["product_id", "week"]).agg(u=("quantity", "sum"), v=("sales_value", "sum"),
                                            d=("retail_disc", "sum")).reset_index()
units = wk.pivot(index="product_id", columns="week", values="u").reindex(columns=WEEKS).fillna(0)
weeks_sold = (units > 0).sum(1)
meta = prod.set_index("product_id")
cands = units[weeks_sold >= 48].sum(1).to_frame("tot").join(meta[["product_category"]])
cands["section"] = cands.product_category.map(cat2sec)
chosen = (cands.sort_values("tot", ascending=False).groupby("section").head(PER_SECTION).index.tolist())
print("chosen SKUs", len(chosen))

promo = pyreadr.read_r(f"{SRC}/promotions.rds")[None]
promo = promo[promo.product_id.isin(chosen) & promo.week.isin(WEEKS)]
stores_carrying = sx[sx.product_id.isin(chosen)].groupby("product_id").store_id.nunique()
pm = promo.assign(mail=(promo.mailer_location.astype(str) != "0"),
                  disp=(promo.display_location.astype(str) != "0"))
pm = pm.groupby(["product_id", "week"]).agg(mail=("mail", "sum"), disp=("disp", "sum")).reset_index()
pm["mail"] = pm.mail / pm.product_id.map(stores_carrying)
pm["disp"] = pm.disp / pm.product_id.map(stores_carrying)
mail = pm.pivot(index="product_id", columns="week", values="mail").reindex(index=chosen, columns=WEEKS).fillna(0).clip(upper=1)
disp = pm.pivot(index="product_id", columns="week", values="disp").reindex(index=chosen, columns=WEEKS).fillna(0).clip(upper=1)
print("mailer share quantiles", np.quantile(mail.values, [.5, .75, .9, .95]).round(3))
MAIL_T = 0.25                        # featured in the mailer at >=25% of the stores carrying it
is_promo = mail >= MAIL_T

vals = wk.pivot(index="product_id", columns="week", values="v").reindex(index=chosen, columns=WEEKS).fillna(0)
disc = wk.pivot(index="product_id", columns="week", values="d").reindex(index=chosen, columns=WEEKS).fillna(0)
U = units.loc[chosen]

skus = []
for pid in chosen:
    u = U.loc[pid].values.astype(float)
    pr = is_promo.loc[pid].values
    base = u[~pr].mean() if (~pr).sum() >= 8 else u.mean()
    lift = (u[pr].mean() / base) if pr.sum() >= 2 and base > 0 else None
    price = vals.loc[pid].sum() / max(u.sum(), 1)
    depth = disc.loc[pid].sum() / max(vals.loc[pid].sum() + disc.loc[pid].sum(), 1e-9)
    m = meta.loc[pid]
    avg = u.mean()
    pack = 6 if avg < 15 else 12 if avg < 60 else 24           # SIMULATED supplier constraint
    skus.append({
        "id": pid, "name": label(m), "section": cat2sec[m.product_category],
        "cat": m.product_category.title(), "brand": str(m.brand), "supplier": f"Supplier {m.manufacturer_id}",
        "units": [int(x) for x in u], "promo": [int(x) for x in pr],
        "mail": [round(float(x), 2) for x in mail.loc[pid].values],
        "disp": [round(float(x), 2) for x in disp.loc[pid].values],
        "price": round(float(price), 2), "disc_depth": round(float(depth), 3),
        "base": round(float(base), 1), "lift": None if lift is None else round(float(lift), 2),
        "pack": pack, "moq_cases": 1, "lead_wk": 1,
    })

# ================================================================== 3. INVENTORY SIMULATION
# Weekly review, 1-week lead time. Demand = real weekly units. Two ordering policies:
#   legacy      : order up to 2x last week's sales (a common habit; ignores the mailer)
#   recommended : promo-aware forecast for the next 2 weeks + safety stock, in case packs
Z = 1.65


def simulate(sk, policy):
    u = np.array(sk["units"], float)
    pr = np.array(sk["promo"], bool)
    lift = sk["lift"] or 1.0
    base = u[:4].mean()                         # EWMA of de-promoted demand
    resid = []
    on = int(np.ceil(2 * u[:2].mean()))
    pipe = 0
    on_hand, lost, orders = [], [], []
    for w in range(len(u)):
        on += pipe
        on_hand.append(on)
        sold = min(on, u[w])
        lost.append(int(u[w] - sold))
        on -= int(sold)
        # learn
        obs = u[w] / (lift if pr[w] else 1.0)
        f_prev = base
        base = 0.3 * obs + 0.7 * base
        resid.append(obs - f_prev)
        # order now, arrives next week
        if policy == "legacy":
            target = 2 * u[w]
        else:
            f1 = base * (lift if (w + 1 < len(u) and pr[w + 1]) else 1.0)
            f2 = base * (lift if (w + 2 < len(u) and pr[w + 2]) else 1.0)
            sd = np.std(resid[-8:]) if len(resid) >= 3 else base * 0.3
            target = f1 + f2 + Z * sd * np.sqrt(2)
        need = max(0.0, target - on)
        q = int(np.ceil(need / sk["pack"]) * sk["pack"]) if need > 0 else 0
        orders.append(q)
        pipe = q
    return on_hand, lost, orders


tot = {"legacy": [0, 0, 0, 0, 0], "recommended": [0, 0, 0, 0, 0]}   # demand, lost, promo demand, promo lost, on-hand
for sk in skus:
    for pol in ["legacy", "recommended"]:
        oh, lo, od = simulate(sk, pol)
        key = "oh_legacy" if pol == "legacy" else "oh_rec"
        sk[key] = oh
        sk["lost_legacy" if pol == "legacy" else "lost_rec"] = lo
        u = np.array(sk["units"]); pr = np.array(sk["promo"], bool); lo = np.array(lo)
        tot[pol][0] += u.sum(); tot[pol][1] += lo.sum()
        tot[pol][2] += u[pr].sum(); tot[pol][3] += lo[pr].sum(); tot[pol][4] += np.sum(oh)
sim = {pol: {"fill": round(1 - v[1] / v[0], 4), "promo_fill": round(1 - v[3] / max(v[2], 1), 4),
             "lost": int(v[1]), "cover_wks": round(v[4] / v[0], 2)} for pol, v in tot.items()}
print("simulation", sim)

lift_by_sec = {}
for sec in SECTIONS:
    ls = [s["lift"] for s in skus if s["section"] == sec and s["lift"]]
    lift_by_sec[sec] = {"median_lift": round(float(np.median(ls)), 2) if ls else None, "n_promo_skus": len(ls),
                        "promo_weeks": int(sum(sum(s["promo"]) for s in skus if s["section"] == sec))}

out = {
    "source": {"name": "84.51° The Complete Journey (2017)", "url": "https://www.8451.com/area51/",
               "pkg": "https://github.com/bradleyboehmke/completejourney",
               "households": 2469, "lines": int(len(tx)), "mail_threshold": MAIL_T, "z": Z},
    "weeks": WEEKS, "sections": list(SECTIONS), "skus": skus, "audit": audit,
    "sim": sim, "lift_by_section": lift_by_sec,
}
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("/* generated by analysis/store_ops.py — do not edit by hand */\n")
    fh.write("window.DATA_STORE = " + json.dumps(out, separators=(",", ":")) + ";\n")
print("wrote", OUT)
