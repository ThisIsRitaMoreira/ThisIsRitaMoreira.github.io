"""
Retail & grocery operations, part 2: what promotions really do, and what sells together.

Source  : 84.51° "The Complete Journey" (via the `completejourney` R package): one year
          (2017) of grocery transactions from 2,469 households across the chain's stores,
          plus weekly in-store display and mailer promotions.
          https://github.com/bradleyboehmke/completejourney · https://www.8451.com/area51/
REAL    : products, categories, weekly units and sales, loyalty-card discounts,
          mailer/display weeks, every basket.
ASSUMED (clearly labelled): the order-planning model at the end (unit cost, vendor
          funding, case packs, supplier minimums, space per case, leftover cost, budget
          and capacity). Demand, lift and prices in it are real.

What it does
  1. PROMOTIONS  For the 12 largest food categories, splits the effect of a mailer
                 promotion into gross lift on the promoted SKU, cannibalisation of the rest
                 of the category, and the post-promotion dip (pantry loading).
  2. BASKETS     Market-basket analysis at category level over every basket: support,
                 confidence, lift (plain and basket-size adjusted), plus a small network.
  3. ORDER LP    Takes one real mailer week and sets up the section manager's order problem
                 (solved here with scipy; analysis/build_solver_workbook.py turns the same
                 numbers into the Excel Solver workbook and checks the answer again).
  4. TABLEAU     A tidy SKU-week extract for a Tableau Public dashboard.

Usage   : python -I retail_promo_basket.py <dir with products.rda, transactions.rds, promotions.rds>
                    <pylib dir with pyreadr> <site root>
Writes  : <site>/data/retail_extra.js  and  <site>/downloads/tableau/promo_performance.csv
"""
import json
import math
import os
import sys

sys.path.insert(0, sys.argv[2])
import numpy as np
import pandas as pd
import pyreadr
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

SRC, SITE = sys.argv[1].rstrip("/\\"), sys.argv[3].rstrip("/\\")
OUT_JS = os.path.join(SITE, "data", "retail_extra.js")
OUT_CSV = os.path.join(SITE, "downloads", "tableau", "promo_performance.csv")
WEEKS = np.arange(1, 53)              # transactions used: weeks 1-52 (as in store_ops.py)
AW = np.arange(2, 53)                 # weekly promo analysis: week 1 is a single day (Jan 1), so it starts at week 2
NW = len(AW)
MAIL_T = 0.25                         # "in the mailer": listed at >=25% of the stores carrying it (same rule as store_ops.py)
DISP_T = 0.25                         # same rule for in-store display support
EXT_PP = 0.05                         # price cut still running: discount >=5 pts deeper than the SKU's ordinary weeks...
EXT_MAX = 2                           # ...for at most 2 weeks after the mailer week
POST_WKS = 2                          # post-promotion window (after the price is back to normal)
MIN_WEEKS_SOLD = 20                   # SKUs in scope: sold in >=20 of the 51 weeks...
MIN_NORMAL_WKS = 8                    # ...with >=8 ordinary weeks to learn a baseline...
LIFE_WKS = 6                          # ...and on sale all year: first sale in weeks 2-7, last in weeks 47-52 (no launches/delists)
BASE_WIN = (6, 13)                    # local baseline window (+/- weeks), widened if too few ordinary weeks
MIN_CAT_SHARE = 0.005                 # basket analysis: categories in >=0.5% of baskets
MIN_PAIR_SUPPORT = 0.005              # pairs bought together in >=0.5% of baskets
NET_LIFT, NET_SUPPORT = 1.5, 0.01     # network edges
EXCLUDE_DEPTS = {"FUEL", "MISCELLANEOUS", "KIOSK-GAS", "POSTAL CENTER", "COUPON", "GM MERCH EXP",
                 "PHOTO", "VIDEO", "TRAVEL & LEISURE", "TRAVEL & LEISUR", "CNTRL/STORE SUP", "RX",
                 "PHARMACY SUPPLY", "CHARITABLE CONT", "VIDEO RENTAL", "POSTAL", "COUP/STR & MFG",
                 "PHOTO & VIDEO", "PROD-WHS SALES", "AUTOMOTIVE", "ELECT &PLUMBING", "TOYS"}

# the 12 largest food categories by sales (alcohol, tobacco and non-food left out)
CATS = {
    "SOFT DRINKS": ("Soft drinks", "Drinks"),
    "BEEF": ("Beef", "Meat & deli"),
    "FLUID MILK PRODUCTS": ("Milk", "Dairy"),
    "CHEESE": ("Cheese", "Dairy"),
    "FRZN MEAT/MEAT DINNERS": ("Frozen meals", "Frozen"),
    "BAG SNACKS": ("Bagged snacks", "Pantry & snacks"),
    "BAKED BREAD/BUNS/ROLLS": ("Bread & rolls", "Bakery"),
    "FROZEN PIZZA": ("Frozen pizza", "Frozen"),
    "COLD CEREAL": ("Cold cereal", "Pantry & snacks"),
    "LUNCHMEAT": ("Lunchmeat", "Meat & deli"),
    "ICE CREAM/MILK/SHERBTS": ("Ice cream", "Frozen"),
    "YOGURT": ("Yogurt", "Dairy"),
}
STORAGE = {"Drinks": "Ambient", "Pantry & snacks": "Ambient", "Bakery": "Ambient",
           "Dairy": "Chilled", "Meat & deli": "Chilled", "Frozen": "Frozen"}


def r(x, n=1):
    if x is None:
        return None
    x = float(x)
    return None if not math.isfinite(x) else (int(round(x)) if n == 0 else round(x, n))


PT_NAMES = {"SFT DRNK 2 LITER BTL CARB INCL": "Soft Drink 2-Litre Bottle",
            "SOFT DRINKS 12/18&15PK CAN CAR": "Soft Drink 12/15/18-Pack Cans",
            "SFT DRNK SNGL SRV BTL CARB (EX": "Soft Drink Single-Serve Bottle",
            "IWS SINGLE CHEESE": "Cheese Singles (Wrapped Slices)", "FLUID MILK WHITE ONLY": "White Milk",
            "YOGURT NOT MULTI-PACKS": "Yogurt Cup", "PIZZA/ECONOMY": "Economy Pizza", "PIZZA/PREMIUM": "Premium Pizza",
            "TORTILLA/NACHO CHIPS": "Tortilla Chips", "POTATO CHIPS": "Potato Chips"}


def label(pid):
    m = meta.loc[pid]
    if pd.notna(m.product_type):
        pt = PT_NAMES.get(m.product_type)
        if pt is None:
            pt = str(m.product_type).title().replace("/", " / ")
            if len(pt) <= 10:                       # e.g. BEEF / "LEAN": say what it is
                pt = f"{str(m.product_category).title()} - {pt}"
    else:
        pt = str(m.product_category).title()
    size = f" · {m.package_size}" if pd.notna(m.package_size) else ""
    own = " · Own brand" if m.brand == "Private" else ""
    return f"{pt}{size}{own}"


CAT_NAMES = {   # readable names for categories that appear in the outputs
    "FLUID MILK PRODUCTS": "Milk", "CHEESES": "Deli Cheese", "BAKED BREAD/BUNS/ROLLS": "Bread, Buns & Rolls",
    "FRZN MEAT/MEAT DINNERS": "Frozen Meals", "ICE CREAM/MILK/SHERBTS": "Ice Cream", "HISPANIC": "International Foods",
    "VEGETABLES SALAD": "Salad Vegetables", "VEGETABLES - ALL OTHERS": "Other Vegetables", "DINNER MXS:DRY": "Dry Dinner Mixes",
    "BEANS - CANNED GLASS & MW": "Canned Beans", "MEAT - SHELF STABLE": "Canned Meat", "SEAFOOD - SHELF STABLE": "Canned Seafood",
    "VEGETABLES - SHELF STABLE": "Canned Vegetables", "FRUIT - SHELF STABLE": "Canned Fruit",
    "DRY BN/VEG/POTATO/RICE": "Rice, Beans & Potato Sides", "PWDR/CRYSTL DRNK MX": "Powdered Drink Mixes",
    "FACIAL TISS/DNR NAPKIN": "Tissues & Napkins", "SALD DRSNG/SNDWCH SPRD": "Salad Dressing & Spreads",
    "PICKLE/RELISH/PKLD VEG": "Pickles & Relish", "HOUSEHOLD CLEANG NEEDS": "Household Cleaning",
    "REFRGRATD DOUGH PRODUCTS": "Refrigerated Dough", "REFRGRATD JUICES/DRNKS": "Refrigerated Juice",
    "CONVENIENT BRKFST/WHLSM SNACKS": "Breakfast & Snack Bars", "FROZEN BREAD/DOUGH": "Frozen Bread & Dough",
    "PEPPERS-ALL": "Peppers", "DRY NOODLES/PASTA": "Dry Pasta", "SUGARS/SWEETNERS": "Sugar & Sweeteners",
    "SHORTENING/OIL": "Cooking Oil", "BREAKFAST SAUSAGE/SANDWICHES": "Breakfast Sausage", "DRY SAUCES/GRAVY": "Sauce & Gravy Mixes",
    "PAPER HOUSEWARES": "Paper Plates & Cups", "MISC. DAIRY": "Misc. Chilled (pudding, tortillas, fresh pasta)",
    "MILK BY-PRODUCTS": "Sour Cream, Dips & Cottage Cheese", "FRZN POTATOES": "Frozen Potatoes", "FROZEN MEAT": "Frozen Meat",
    "WATER - CARBONATED/FLVRD DRINK": "Water & Flavored Drinks", "CRACKERS/MISC BKD FD": "Crackers",
    "FRZN VEGETABLE/VEG DSH": "Frozen Vegetables", "FRZN NOVELTIES/WTR ICE": "Frozen Novelties",
    "SOFT DRINKS": "Soft Drinks", "COLD CEREAL": "Cold Cereal", "BAG SNACKS": "Bagged Snacks",
}
WORDS = {"Frzn": "Frozen", "Refrgratd": "Refrigerated", "Drnks": "Drinks", "Drnk": "Drink", "Bkd": "Baked", "Fd": "Food",
         "Sald": "Salad", "Drsng": "Dressing", "Sndwch": "Sandwich", "Sprd": "Spread", "Mxs": "Mixes", "Mx": "Mix",
         "Brkfst": "Breakfast", "Whlsm": "Wholesome", "Dsh": "Dishes", "Sherbts": "Sherbets", "Wtr": "Water",
         "Flvrd": "Flavored", "Trsh": "Trash", "Bg": "Bags", "Prpd": "Prepared", "Dssrt": "Dessert", "Pnt": "Peanut",
         "Btr": "Butter", "Jlly": "Jelly", "Hmbrgr": "Hamburger", "Bkng": "Baking", "Grnd": "Ground", "Dinnr": "Dinner",
         "Dnr": "Dinner", "Ingrdnts": "Ingredients", "Frstng": "Frosting", "Bns": "Buns", "Sce": "Sauce", "Pkgd": "Packaged",
         "Cnd": "Canned", "Hsehld": "Household", "Cleang": "Cleaning", "Tiss": "Tissues", "Pwdr": "Powdered",
         "Crystl": "Crystal", "Sweetners": "Sweeteners", "Pkld": "Pickled", "Mw": "Microwave"}


def nice(cat):
    if cat in CAT_NAMES:
        return CAT_NAMES[cat]
    t = cat.title().replace("/", " / ").replace("&", " & ")
    t = " ".join(WORDS.get(w, w) for w in t.split())
    return t


# ================================================================== LOAD
prod = pyreadr.read_r(f"{SRC}/products.rda")["products"]
meta = prod.set_index("product_id")
tx = pyreadr.read_r(f"{SRC}/transactions.rds")[None]
tx = tx[tx.week.isin(WEEKS)].merge(prod, on="product_id", how="left")
tx = tx[~tx.department.isin(EXCLUDE_DEPTS) & tx.product_category.notna()
        & (tx.product_category != "COUPON/MISC ITEMS") & (tx.quantity > 0)]
week_start = tx.groupby("week").transaction_timestamp.min().dt.normalize().reindex(AW)
n_baskets_wk = tx.groupby("week").basket_id.nunique().reindex(AW).values.astype(float)
N_LINES, N_BASKETS, N_HH = int(len(tx)), int(tx.basket_id.nunique()), int(tx.household_id.nunique())
print("lines", N_LINES, "baskets", N_BASKETS, "households", N_HH)

cx = tx[tx.product_category.isin(CATS)]
stores_carrying = cx.groupby("product_id").store_id.nunique()
wk = cx.groupby(["product_id", "week"]).agg(u=("quantity", "sum"), v=("sales_value", "sum"),
                                            d=("retail_disc", "sum")).reset_index()
promo = pyreadr.read_r(f"{SRC}/promotions.rds")[None]
promo = promo[promo.week.isin(AW) & promo.product_id.isin(stores_carrying.index)]
pm = promo.assign(mail=(promo.mailer_location.astype(str) != "0"), disp=(promo.display_location.astype(str) != "0"))
pm = pm.groupby(["product_id", "week"]).agg(mail=("mail", "sum"), disp=("disp", "sum")).reset_index()
del promo


def mat(df, col, idx):
    return df.pivot(index="product_id", columns="week", values=col).reindex(index=idx, columns=AW).fillna(0)


# ================================================================== 1. PROMOTIONS
def local_baseline(u, normal):
    """Leave-one-out mean of the SKU's ordinary weeks within +/-6 weeks (widened to +/-13,
    then the whole year, when fewer than 4 ordinary weeks are available)."""
    S = u.shape[0]
    un, nn = np.where(normal, u, 0.0), normal.astype(float)
    cu = np.concatenate([np.zeros((S, 1)), un.cumsum(1)], 1)
    cn = np.concatenate([np.zeros((S, 1)), nn.cumsum(1)], 1)
    b = np.full(u.shape, np.nan)
    for h in BASE_WIN:
        lo, hi = np.clip(np.arange(NW) - h, 0, NW), np.clip(np.arange(NW) + h + 1, 0, NW)
        s, c = cu[:, hi] - cu[:, lo] - un, cn[:, hi] - cn[:, lo] - nn
        ok = np.isnan(b) & (c >= 4)
        b[ok] = (s / np.where(c > 0, c, 1))[ok]
    tot_s, tot_c = un.sum(1, keepdims=True) - un, nn.sum(1, keepdims=True) - nn
    full = np.broadcast_to(tot_s / np.where(tot_c > 0, tot_c, 1), u.shape)
    b[np.isnan(b)] = full[np.isnan(b)]
    return b


def runs(flags):
    """[(start, end)] index pairs of consecutive True runs."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        if not f and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def ols(y, cols):
    X = np.column_stack([np.ones(len(y))] + list(cols))
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    s2 = res @ res / (len(y) - np.linalg.matrix_rank(X))
    return beta, np.sqrt(np.diag(s2 * np.linalg.pinv(X.T @ X)))


def loo_mean(x, h=6):
    return np.array([np.mean(np.delete(x[max(0, w - h):w + h + 1], min(w, h))) for w in range(len(x))])


traffic = n_baskets_wk / loo_mean(n_baskets_wk) - 1      # store-traffic shock vs the surrounding weeks

cat_rows, events_all, store = [], [], {}
shelf_tot = [0.0, 0.0]
for cat, (clabel, section) in CATS.items():
    ids = cx.loc[cx.product_category == cat, "product_id"].unique()
    U, V, D = (mat(wk, c, ids) for c in ("u", "v", "d"))
    sub = pm[pm.product_id.isin(ids)].copy()
    sub["mail"] = sub.mail / sub.product_id.map(stores_carrying)
    sub["disp"] = sub.disp / sub.product_id.map(stores_carrying)
    MS, DS = mat(sub, "mail", ids).clip(upper=1), mat(sub, "disp", ids).clip(upper=1)
    u, v, d = U.values.astype(float), V.values, D.values
    ms, ds = MS.values, DS.values
    mail = ms >= MAIL_T
    depth = np.where(u > 0, d / np.maximum(v + d, 1e-9), np.nan)
    # ordinary-week discount depth per SKU (first pass: weeks with no mailer in the 2 weeks before)
    near = mail.copy()
    for k in range(1, POST_WKS + 1):
        near[:, k:] |= mail[:, :-k]
    dd, vv = np.where(~near, d, 0).sum(1), np.where(~near, v, 0).sum(1)
    depth_ord = dd / np.maximum(dd + vv, 1e-9)
    # extension: the loyalty-card price cut often outlasts the mailer week
    ext = np.zeros_like(mail)
    ext_len = np.zeros(len(ids), int)              # consecutive extension weeks so far
    cut = np.nan_to_num(depth, nan=0) >= depth_ord[:, None] + EXT_PP
    for w in range(1, NW):
        ext[:, w] = (mail[:, w - 1] | ext[:, w - 1]) & ~mail[:, w] & cut[:, w] & (ext_len < EXT_MAX)
        ext_len = np.where(ext[:, w], ext_len + 1, 0)
    P = mail | ext
    post = np.zeros_like(P)
    for k in range(1, POST_WKS + 1):
        post[:, k:] |= P[:, :-k]
    post &= ~P
    normal = ~P & ~post
    sold = u > 0
    in_scope = ((sold.sum(1) >= MIN_WEEKS_SOLD) & (normal.sum(1) >= MIN_NORMAL_WKS)
                & sold[:, :LIFE_WKS].any(1) & sold[:, -LIFE_WKS:].any(1))
    cover = u[in_scope].sum() / u.sum()
    ids_s = U.index[in_scope]
    u, v, d, ms, ds = u[in_scope], v[in_scope], d[in_scope], ms[in_scope], ds[in_scope]
    mail, ext, P, post, normal = mail[in_scope], ext[in_scope], P[in_scope], post[in_scope], normal[in_scope]
    depth, depth_ord = depth[in_scope], depth_ord[in_scope]
    b = local_baseline(u, normal)

    gross_w = np.where(P, u - b, 0).sum(0)
    dip_w = np.where(post, b - u, 0).sum(0)
    rest_dev_w = np.where(normal, u - b, 0).sum(0)
    rest_base_w = np.where(normal, b, 0).sum(0)
    rest_price_w = np.where(normal, b * np.nan_to_num(depth - depth_ord[:, None]), 0).sum(0)
    # cannibalisation: how far the ordinary (non-promoted) SKUs fall below their own baseline as
    # promo pressure rises, controlling for store traffic and for their own price cuts.
    beta, se = ols(rest_dev_w, [gross_w, traffic * rest_base_w, rest_price_w])
    rate, rate_se = -beta[1], se[1]
    gross = gross_w.sum()
    gross_ext = np.where(ext, u - b, 0).sum()
    cannib = max(rate, 0.0) * gross            # a negative rate (halo) is reported but never credited
    dip = dip_w.sum()
    net = gross - cannib - dip
    promo_units, base_in_promo = u[P].sum(), b[P].sum()
    disc_usd = d[P].sum()
    shelf_price = (v[normal].sum() + d[normal].sum()) / u[normal].sum()
    shelf_tot[0] += v[normal].sum() + d[normal].sum()
    shelf_tot[1] += u[normal].sum()

    n_ev = 0
    for i, pid in enumerate(ids_s):
        for s0, e0 in runs(P[i]):
            n_ev += 1
            wks = np.arange(s0, e0 + 1)
            pw = [w for w in range(e0 + 1, min(NW, e0 + 1 + POST_WKS)) if post[i, w]]
            events_all.append({
                "cat": cat, "pid": pid, "i": i, "start": int(s0), "end": int(e0),
                "mail_wks": int(mail[i, wks].sum()), "ext_wks": int(ext[i, wks].sum()),
                "base": b[i, wks].sum(), "units": u[i, wks].sum(), "gross": (u[i, wks] - b[i, wks]).sum(),
                "dip": (b[i, pw] - u[i, pw]).sum() if pw else 0.0, "post_base": b[i, pw].sum() if pw else 0.0,
                "depth": d[i, wks].sum() / max(v[i, wks].sum() + d[i, wks].sum(), 1e-9),
                "display": bool((ds[i, wks] >= DISP_T).any()),
            })

    row = {
        "cat": cat, "label": clabel, "section": section,
        "skus": int(in_scope.sum()), "skus_all": int(len(ids)), "coverage": r(cover, 3),
        "base_wk": r(b.sum(0).mean(), 0), "units_wk": r(u.sum(0).mean(), 0),
        "events": n_ev, "mail_sku_weeks": int(mail.sum()), "ext_sku_weeks": int(ext.sum()),
        "promo_unit_share": r(promo_units / u.sum(), 3),
        "promo_units": r(promo_units, 0), "base_in_promo": r(base_in_promo, 0),
        "gross": r(gross, 0), "gross_ext": r(gross_ext, 0), "gross_pct": r(gross / base_in_promo, 3),
        "cannib": r(cannib, 0), "cannib_rate": r(rate, 3),
        "cannib_ci": [r(rate - 1.96 * rate_se, 3), r(rate + 1.96 * rate_se, 3)],
        "halo": bool(rate < 0),
        "dip": r(dip, 0), "dip_pct_base": r(dip / max(np.where(post, b, 0).sum(), 1e-9), 3),
        "net": r(net, 0), "net_pct": r(net / gross, 3),
        "net_per_100": r(100 * net / promo_units, 1),
        "disc_promo": r(d[P].sum() / (v[P].sum() + d[P].sum()), 3),
        "disc_normal": r(d[normal].sum() / (v[normal].sum() + d[normal].sum()), 3),
        "disc_usd": r(disc_usd, 0), "disc_per_net_unit": r(disc_usd / net, 2) if net > 0 else None,
        "shelf_price": r(shelf_price, 2),
    }
    cat_rows.append(row)
    store[cat] = dict(ids=ids_s, u=u, b=b, P=P, mail=mail, ext=ext, post=post, normal=normal,
                      v=v, d=d, ms=ms, ds=ds, depth=depth, depth_ord=depth_ord)
    print(f"{clabel:14s} skus {row['skus']:4d} cov {cover:.2f} ev {n_ev:4d} gross {gross:7.0f} (+{row['gross_pct']:.0%}, ext {gross_ext:5.0f}) "
          f"cannib {cannib:6.0f} (rate {rate:+.2f} ± {1.96 * rate_se:.2f}) dip {dip:6.0f} ({row['dip_pct_base']:+.0%}) "
          f"net {net:7.0f} ({row['net_pct']:.0%}) depth {row['disc_promo']:.0%}/{row['disc_normal']:.0%} "
          f"$disc/net unit {row['disc_per_net_unit']} vs shelf {shelf_price:.2f}")

ev = pd.DataFrame(events_all)
T = {k: float(sum(c[k] for c in cat_rows)) for k in ("gross", "cannib", "dip", "net", "promo_units", "base_in_promo", "disc_usd", "gross_ext")}
totals = {
    "gross": r(T["gross"], 0), "cannib": r(T["cannib"], 0), "dip": r(T["dip"], 0), "net": r(T["net"], 0),
    "net_pct": r(T["net"] / T["gross"], 3), "promo_units": r(T["promo_units"], 0),
    "base_in_promo": r(T["base_in_promo"], 0), "subsidised_share": r(T["base_in_promo"] / T["promo_units"], 3),
    "gross_ext": r(T["gross_ext"], 0), "events": int(len(ev)), "disc_usd": r(T["disc_usd"], 0),
    "disc_per_net_unit": r(T["disc_usd"] / T["net"], 2),
}
print("TOTAL", totals)

# lift by discount depth and by display support (event level, events with a usable baseline)
evq = ev[ev.base >= 5].copy()
bands = [(0, .2, "under 20%"), (.2, .3, "20-30%"), (.3, .4, "30-40%"), (.4, .5, "40-50%"), (.5, 1.01, "50%+")]
depth_bands = []
for lo, hi, name in bands:
    g = evq[(evq.depth >= lo) & (evq.depth < hi)]
    depth_bands.append({"band": name, "events": int(len(g)), "lift_pct": r(g.gross.sum() / g.base.sum(), 3) if len(g) else None,
                        "median_event_lift": r(float(np.median(g.gross / g.base)), 3) if len(g) else None})
disp_eff = {}
for flag, name in [(True, "with_display"), (False, "mailer_only")]:
    g = evq[evq.display == flag]
    disp_eff[name] = {"events": int(len(g)), "lift_pct": r(g.gross.sum() / g.base.sum(), 3), "depth": r(float(np.median(g.depth)), 3)}
# same comparison inside matched depth bands, so display isn't just standing in for deeper discounts
disp_by_band = []
for lo, hi, name in bands[1:4]:
    g = evq[(evq.depth >= lo) & (evq.depth < hi)]
    a, c = g[g.display], g[~g.display]
    if len(a) >= 20 and len(c) >= 20:
        disp_by_band.append({"band": name, "with_display": r(a.gross.sum() / a.base.sum(), 3),
                             "mailer_only": r(c.gross.sum() / c.base.sum(), 3), "n_display": int(len(a)), "n_mailer": int(len(c))})
print("depth bands", depth_bands)
print("display", disp_eff, disp_by_band)

# ------------------------------------------------------------------ example timelines
def example(cat, i, why, title):
    s = store[cat]
    u, b, P, post, normal = s["u"], s["b"], s["P"], s["post"], s["normal"]
    state = np.where(s["mail"][i], 1, np.where(s["ext"][i], 2, np.where(post[i], 3, 0)))
    others = np.ones(len(u), bool)
    others[i] = False
    on = normal & others[:, None]
    e = ev[(ev.cat == cat) & (ev.i == i)]
    pid = s["ids"][i]
    return {
        "id": str(pid), "name": label(pid), "cat": CATS[cat][0], "brand": str(meta.loc[pid, "brand"]),
        "title": title, "why": why,
        "units": [int(x) for x in u[i]], "base": [r(x, 1) for x in b[i]], "state": [int(x) for x in state],
        "depth": [r(x, 2) if np.isfinite(x) else None for x in s["depth"][i]],
        "rest_units": [int(x) for x in np.where(on, u, 0).sum(0)],
        "rest_base": [r(x, 0) for x in np.where(on, b, 0).sum(0)],
        "summary": {"events": int(len(e)), "base_wk": r(b[i][normal[i]].mean() if normal[i].any() else b[i].mean(), 1),
                    "gross": r(e.gross.sum(), 0), "gross_pct": r(e.gross.sum() / e.base.sum(), 3),
                    "dip": r(e.dip.sum(), 0), "dip_pct": r(e.dip.sum() / max(e.post_base.sum(), 1e-9), 3),
                    "depth": r(float((e.depth * e.base).sum() / e.base.sum()), 3),
                    # rest of the category (its other SKUs in ordinary weeks) vs their baseline: in this SKU's mailer weeks / other weeks
                    "rest_idx_mailer": r(np.where(on, u, 0).sum(0)[s["mail"][i]].sum() / np.where(on, b, 0).sum(0)[s["mail"][i]].sum(), 3),
                    "rest_idx_other": r(np.where(on, u, 0).sum(0)[~P[i]].sum() / np.where(on, b, 0).sum(0)[~P[i]].sum(), 3)},
    }


sku_ev = ev.groupby(["cat", "i"]).agg(n=("gross", "size"), gross=("gross", "sum"), base=("base", "sum"),
                                      dip=("dip", "sum"), post_base=("post_base", "sum")).reset_index()
sku_ev["gpct"] = sku_ev.gross / sku_ev.base
sku_ev["dpct"] = sku_ev.dip / sku_ev.post_base.clip(lower=1e-9)
sku_ev["bwk"] = [store[c]["b"][i][store[c]["normal"][i]].mean() for c, i in zip(sku_ev.cat, sku_ev.i)]
ok = sku_ev[(sku_ev.n >= 4) & (sku_ev.bwk >= 8)]
# 1) cannibalisation: the category whose rate is most clearly above zero (lower CI bound), its biggest promoted SKU
can_cat = max(cat_rows, key=lambda c: c["cannib_ci"][0])["cat"]
ex_can = ok[ok["cat"] == can_cat].sort_values("gross", ascending=False).iloc[0]
# 2) a big spike that mostly adds: another category, no visible dip afterwards
ex_spike = ok[(ok["cat"] != can_cat) & (ok.dpct <= 0.05) & (ok.gpct >= 1.5)].sort_values("gross", ascending=False).iloc[0]
# 3) pantry loading: the biggest dip in units among SKUs whose post-promo weeks fall >=15% below baseline
ex_dip = ok[~ok["cat"].isin([can_cat, ex_spike["cat"]]) & (ok.dpct >= 0.15)].sort_values("dip", ascending=False).iloc[0]
examples = [
    example(ex_spike["cat"], int(ex_spike.i), "spike", "A promotion that mostly adds"),
    example(ex_dip["cat"], int(ex_dip.i), "dip", "Pantry loading: the weeks after give some back"),
    example(ex_can["cat"], int(ex_can.i), "cannibalisation", "Borrowing from the shelf next door"),
]
for e in examples:
    print("example", e["why"], e["cat"], e["name"], e["summary"])

# ================================================================== 2. MARKET BASKET
bk = tx[["basket_id", "product_category"]].drop_duplicates()
cat_n_all = bk.product_category.value_counts()
keep = cat_n_all[cat_n_all >= MIN_CAT_SHARE * N_BASKETS].index
bk = bk[bk.product_category.isin(keep)]
bi, bas = pd.factorize(bk.basket_id)
ci, cats = pd.factorize(bk.product_category)
X = sparse.csr_matrix((np.ones(len(bk)), (bi, ci)), shape=(len(bas), len(cats)))
N = N_BASKETS                                     # all merchandise baskets (incl. ones with only tiny categories)
n_c = np.asarray(X.sum(0)).ravel()
C = (X.T @ X).toarray()
# basket-size-adjusted expectation: independence within basket-size strata
size = np.asarray(X.sum(1)).ravel()
strata = np.digitize(size, [3, 5, 8, 12, 18, 26])
E = np.zeros_like(C)
for s_ in np.unique(strata):
    rows = strata == s_
    Ns = rows.sum()
    p = np.asarray(X[rows].sum(0)).ravel() / Ns
    E += Ns * np.outer(p, p)
dept_of = tx.groupby("product_category").department.agg(lambda x: x.value_counts().index[0])

FRESH = {"PRODUCE", "MEAT", "MEAT-PCKGD", "DELI", "SEAFOOD", "SEAFOOD-PCKGD", "PASTRY", "SALAD BAR", "FLORAL", "CHEF SHOPPE", "RESTAURANT"}
NONFOOD = {"DRUG GM", "COSMETICS", "GARDEN CENTER", "HOUSEWARES"}


def zone(cat):
    dpt = dept_of.get(cat, "")
    if dpt in FRESH:
        return "Fresh"
    if dpt in NONFOOD:
        return "Non-food"
    if dpt == "SPIRITS" or any(k in cat for k in ("SOFT DRINK", "WATER", "JUICE", "COFFEE", "TEA", "BEER", "WINE", "DRINK")):
        return "Drinks"
    if any(k in cat for k in ("MILK", "CHEESE", "YOGURT", "EGGS", "FROZEN", "FRZN", "ICE CREAM", "REFRGRATD",
                              "BUTTER", "MARGARINE", "DOUGH", "NOVELTIES")):
        return "Dairy & frozen"
    if dpt in ("GROCERY", "NUTRITION", "FROZEN GROCERY"):
        return "Pantry"
    return "Other"


cat_tbl = [{"cat": c, "label": nice(c), "dept": str(dept_of.get(c, "")).title(), "zone": zone(c),
            "baskets": int(n), "pen": r(n / N, 4)} for c, n in sorted(zip(cats, n_c), key=lambda t: -t[1])]
iu, ju = np.triu_indices(len(cats), 1)
pairs = pd.DataFrame({"a": cats[iu], "b": cats[ju], "n": C[iu, ju], "na": n_c[iu], "nb": n_c[ju], "e_adj": E[iu, ju]})
pairs["support"] = pairs.n / N
pairs["conf_ab"] = pairs.n / pairs.na
pairs["conf_ba"] = pairs.n / pairs.nb
pairs["lift"] = pairs.n * N / (pairs.na * pairs.nb)
pairs["lift_adj"] = pairs.n / pairs.e_adj
pairs["cross"] = [zone(a) != zone(b) for a, b in zip(pairs.a, pairs.b)]
pairs = pairs[pairs.support >= MIN_PAIR_SUPPORT]
top = pairs.sort_values("lift", ascending=False).head(40)
print("categories kept", len(cats), "pairs >= min support", len(pairs))
print(top[["a", "b", "n", "support", "conf_ab", "conf_ba", "lift", "lift_adj"]].head(40).to_string())


def pair_row(p):
    return {"a": p.a, "b": p.b, "a_label": nice(p.a), "b_label": nice(p.b), "n": int(p.n),
            "support": r(p.support, 4), "conf_ab": r(p.conf_ab, 3), "conf_ba": r(p.conf_ba, 3),
            "lift": r(p.lift, 2), "lift_adj": r(p.lift_adj, 2), "cross_zone": bool(p.cross)}


# network
edges = pairs[(pairs.lift >= NET_LIFT) & (pairs.support >= NET_SUPPORT)].sort_values("lift", ascending=False).head(70)
nodes = sorted(set(edges.a) | set(edges.b))
idx = {c: k for k, c in enumerate(nodes)}
rng = np.random.default_rng(7)
pos = rng.random((len(nodes), 2))
A = np.zeros((len(nodes), len(nodes)))
for _, e in edges.iterrows():
    A[idx[e.a], idx[e.b]] = A[idx[e.b], idx[e.a]] = e.lift - 1
k_ = 1 / math.sqrt(len(nodes))
t_ = 0.1
for it in range(600):                              # Fruchterman-Reingold
    delta = pos[:, None, :] - pos[None, :, :]
    dist = np.linalg.norm(delta, axis=2) + 1e-6
    rep = (k_ ** 2 / dist ** 2)[:, :, None] * delta
    att = -(A * dist / k_)[:, :, None] * delta
    disp_ = (rep + att).sum(1)
    ln = np.linalg.norm(disp_, axis=1)[:, None] + 1e-9
    pos += disp_ / ln * np.minimum(ln, t_)
    pos += (0.5 - pos) * 0.01                      # mild gravity keeps islands on screen
    t_ = max(0.002, t_ * 0.992)
pos = (pos - pos.min(0)) / (pos.max(0) - pos.min(0))
pos = 0.06 + 0.88 * pos
pen = dict(zip(cats, n_c / N))
network = {
    "nodes": [{"id": c, "label": nice(c), "zone": zone(c), "pen": r(pen[c], 4), "x": r(pos[idx[c], 0], 3),
               "y": r(pos[idx[c], 1], 3), "degree": int((A[idx[c]] > 0).sum())} for c in nodes],
    "edges": [{"s": e.a, "t": e.b, "lift": r(e.lift, 2), "support": r(e.support, 4)} for _, e in edges.iterrows()],
    "rule": {"min_lift": NET_LIFT, "min_support": NET_SUPPORT},
}
print("network nodes", len(nodes), "edges", len(edges))


def get_pair(a, b):
    m = pairs[((pairs.a == a) & (pairs.b == b)) | ((pairs.a == b) & (pairs.b == a))]
    assert len(m) == 1, (a, b)
    p = m.iloc[0]
    if p.a != a:                                   # orient so that conf_ab means P(b | a)
        p = p.copy()
        p["a"], p["b"], p["na"], p["nb"], p["conf_ab"], p["conf_ba"] = p.b, p.a, p.nb, p.na, p.conf_ba, p.conf_ab
    return p


for a, b in [("DRY NOODLES/PASTA", "PASTA SAUCE"), ("PASTA SAUCE", "FROZEN BREAD/DOUGH"), ("DELI MEATS", "CHEESES"),
             ("HISPANIC", "MISC. DAIRY"), ("HOT DOGS", "BAKED BREAD/BUNS/ROLLS"), ("BACON", "BREAKFAST SAUSAGE/SANDWICHES"),
             ("BACON", "EGGS"), ("ONIONS", "PEPPERS-ALL"), ("SALAD MIX", "SALD DRSNG/SNDWCH SPRD"), ("BAKING MIXES", "BAKING NEEDS"),
             ("BEEF", "BAKED BREAD/BUNS/ROLLS"), ("BAG SNACKS", "SOFT DRINKS"), ("COLD CEREAL", "FLUID MILK PRODUCTS")]:
    try:
        p = get_pair(a, b)
        print(f"PAIR {a} -> {b}: n {int(p.n)} sup {p.support:.3%} conf {p.conf_ab:.2f}/{p.conf_ba:.2f} lift {p.lift:.2f} adj {p.lift_adj:.2f}")
    except AssertionError:
        print("PAIR missing", a, b)

# ================================================================== 3. ORDER LP (one real mailer week)
# REAL: forecast inputs (baseline that week x the SKU's lift in its OTHER mailer weeks), regular and promo prices.
# ASSUMED: everything about cost, packs, minimums, space and leftovers (labelled in the workbook too).
COST_PCT, VENDOR_FUND = 0.70, 0.50                 # unit cost = 70% of regular price; supplier funds 50% of the promo discount
LEFTOVER = {"Ambient": 0.05, "Chilled": 0.20, "Frozen": 0.08}   # cost of a leftover unit, as % of its unit cost
UNIT_FT3 = {"SOFT DRINKS": 0.30, "BEEF": 0.04, "FLUID MILK PRODUCTS": 0.15, "CHEESE": 0.02,
            "FRZN MEAT/MEAT DINNERS": 0.04, "BAG SNACKS": 0.12, "BAKED BREAD/BUNS/ROLLS": 0.12,
            "FROZEN PIZZA": 0.08, "COLD CEREAL": 0.10, "LUNCHMEAT": 0.02, "ICE CREAM/MILK/SHERBTS": 0.06, "YOGURT": 0.02}
BUDGET_SHARE, SPACE_SHARE = 0.78, 0.72             # open-to-buy and space: below what full forecast cover would need
N_LP = 12
LP_WEEK = 28                                       # the July 4th mailer: week starting Monday 3 July 2017
order_scale = 1.0                                  # store scale (multiplies forecast demand; 1 = the panel itself)


def pack_of(base):                                 # same case-pack rule as store_ops.py
    return 6 if base < 15 else 12 if base < 60 else 24


def lp_candidates(w):
    out = []
    for cat, s in store.items():
        for i in np.where(s["mail"][:, w])[0]:
            u, b, v, d = s["u"][i], s["b"][i], s["v"][i], s["d"][i]
            run = next((a, z) for a, z in runs(s["P"][i]) if a <= w <= z)
            other = s["mail"][i].copy()
            other[run[0]:run[1] + 1] = False
            if other.sum() < 2 or b[other].sum() < 20 or b[w] < 10 or u[w] <= 0:
                continue
            lift = u[other].sum() / b[other].sum()
            nm = s["normal"][i]
            reg = (v[nm].sum() + d[nm].sum()) / max(u[nm].sum(), 1e-9)
            promo_p = v[w] / u[w]
            depth_ = 1 - promo_p / reg
            if not (1.2 <= lift <= 8 and 0.10 <= depth_ <= 0.50):
                continue
            out.append({"cat": cat, "i": int(i), "pid": s["ids"][i], "base": float(b[w]), "lift": float(lift),
                        "forecast": float(b[w] * lift), "actual": int(u[w]), "reg": float(reg), "promo": float(promo_p)})
    return out


LPW = int(LP_WEEK - AW[0])
cands = lp_candidates(LPW)
assert len(cands) >= N_LP, f"week {LP_WEEK}: only {len(cands)} usable promoted SKUs"
cands.sort(key=lambda x: -x["forecast"])
chosen, per_cat = [], {}
for rnd in range(3):                               # round-robin across categories: 1st pick of each, then 2nd, ...
    for x in cands:
        if len(chosen) < N_LP and per_cat.get(x["cat"], 0) == rnd and x not in chosen:
            chosen.append(x)
            per_cat[x["cat"]] = rnd + 1
chosen.sort(key=lambda x: (list(CATS).index(x["cat"]), -x["forecast"]))
lp_skus = []
for x in chosen:
    sec = CATS[x["cat"]][1]
    pack = pack_of(x["base"])
    lp_skus.append({
        "id": str(x["pid"]), "name": label(x["pid"]), "supplier": f"Supplier {meta.loc[x['pid'], 'manufacturer_id']}",
        "cat": CATS[x["cat"]][0], "section": sec, "zone": STORAGE[sec],
        "base": r(x["base"], 1), "lift": r(x["lift"], 2), "actual": x["actual"],
        "reg_price": r(x["reg"], 2), "promo_price": r(x["promo"], 2),
        "pack": pack, "min_cases": int(math.ceil(24 / pack)), "ft3_unit": UNIT_FT3[x["cat"]],
        "leftover_pct": LEFTOVER[STORAGE[sec]],
    })
# derived numbers exactly as the workbook computes them (from the rounded inputs above)
for k in lp_skus:
    k["forecast"] = int(math.floor(k["base"] * k["lift"] * order_scale + 0.5))     # Excel ROUND(x, 0): half away from zero
    k["depth"] = round(1 - k["promo_price"] / k["reg_price"], 4)
    k["unit_cost"] = COST_PCT * k["reg_price"] - VENDOR_FUND * (k["reg_price"] - k["promo_price"])
    k["margin"] = k["promo_price"] - k["unit_cost"]
    k["hold"] = k["unit_cost"] * k["leftover_pct"]
    k["ft3_case"] = k["pack"] * k["ft3_unit"]
F = np.array([k["forecast"] for k in lp_skus], float)
pk = np.array([k["pack"] for k in lp_skus], float)
cst = np.array([k["unit_cost"] for k in lp_skus])
mg = np.array([k["margin"] for k in lp_skus])
hd = np.array([k["hold"] for k in lp_skus])
sp = np.array([k["ft3_case"] for k in lp_skus])
mn = np.array([k["min_cases"] for k in lp_skus], float)
full = np.ceil(F / pk)
BUDGET = float(math.floor(BUDGET_SHARE * (cst * pk * full).sum() / 50) * 50)
SPACE = float(math.floor(SPACE_SHARE * (sp * full).sum() / 5) * 5)
n = len(lp_skus)


def solve(integer):
    # variables [x_1..x_n (cases), s_1..s_n (units sold)]; maximise sum m*s - h*(pack*x - s)
    c = -np.concatenate([-hd * pk, mg + hd])
    A = np.zeros((n + 2, 2 * n))
    A[:n, :n] = -np.diag(pk)
    A[:n, n:] = np.eye(n)                           # s_i - pack_i x_i <= 0
    A[n, :n] = cst * pk                             # budget
    A[n + 1, :n] = sp                               # space
    ub = np.concatenate([np.zeros(n), [BUDGET, SPACE]])
    res = milp(c, constraints=LinearConstraint(A, -np.inf, ub),
               integrality=np.r_[np.ones(n) if integer else np.zeros(n), np.zeros(n)],
               bounds=Bounds(np.r_[mn, np.zeros(n)], np.r_[np.full(n, np.inf), F]))
    assert res.success, res.message
    return res.x[:n], res.x[n:], -res.fun


def objective(x, s_):
    return float((mg * s_ - hd * (pk * x - s_)).sum())


x_opt, s_opt, obj_opt = solve(True)
x_opt = np.round(x_opt)
s_opt = np.minimum(F, pk * x_opt)
assert abs(objective(x_opt, s_opt) - obj_opt) < 1e-6
_, _, obj_lp = solve(False)
# rule-of-thumb plan: cover the forecast, then cut every SKU by the same % until budget and space fit...
f = min(1.0, BUDGET / (cst * pk * full).sum(), SPACE / (sp * full).sum())
x_nv = np.maximum(mn, np.floor(full * f))
while (cst * pk * x_nv).sum() > BUDGET + 1e-9 or (sp * x_nv).sum() > SPACE + 1e-9:
    j = int(np.argmax(np.where(x_nv > mn, x_nv, -1)))
    x_nv[j] -= 1
# ...and, like a careful planner, top up the biggest shortfalls (in units) while budget and space allow
while True:
    gap = F - pk * x_nv
    fits = ((cst * pk * x_nv).sum() + cst * pk <= BUDGET + 1e-9) & ((sp * x_nv).sum() + sp <= SPACE + 1e-9) & (gap > 0)
    if not fits.any():
        break
    x_nv[int(np.argmax(np.where(fits, gap, -np.inf)))] += 1
s_nv = np.minimum(F, pk * x_nv)
obj_nv = objective(x_nv, s_nv)
for k, a, b_, c_, d_ in zip(lp_skus, x_opt, s_opt, x_nv, s_nv):
    k.update({"opt_cases": int(a), "opt_sold": int(round(b_)), "opt_left": int(round(a * k["pack"] - b_)),
              "naive_cases": int(c_), "naive_sold": int(round(d_))})
    for f_ in ("unit_cost", "margin", "hold", "ft3_case"):
        k[f_] = round(k[f_], 4)
order_plan = {
    "week": int(AW[LPW]), "week_start": str(week_start.iloc[LPW].date()),
    "assumptions": {"cost_pct_of_regular": COST_PCT, "vendor_funding_of_discount": VENDOR_FUND,
                    "leftover_cost_pct": LEFTOVER, "ft3_per_unit": {CATS[c][0]: v_ for c, v_ in UNIT_FT3.items()},
                    "pack_rule": "6 if baseline < 15 units/wk, 12 if < 60, else 24 (as in the order recommender)",
                    "min_rule": "supplier minimum = 24 units per line, in whole cases",
                    "budget_rule": f"{BUDGET_SHARE:.0%} of the cost of covering every forecast in full, rounded down to $50",
                    "space_rule": f"{SPACE_SHARE:.0%} of the space that full cover would need, rounded down to 5 ft3",
                    "store_scale": order_scale},
    "budget": BUDGET, "space": SPACE, "skus": lp_skus,
    "result": {"objective": r(obj_opt, 2), "lp_relaxation": r(obj_lp, 2), "naive_objective": r(obj_nv, 2),
               "uplift_vs_naive": r(obj_opt - obj_nv, 2),
               "budget_used": r((cst * pk * x_opt).sum(), 2), "space_used": r((sp * x_opt).sum(), 2),
               "units_ordered": int((pk * x_opt).sum()), "units_sold": int(s_opt.sum()), "forecast_units": int(F.sum()),
               "fill_rate": r(s_opt.sum() / F.sum(), 3), "naive_fill_rate": r(s_nv.sum() / F.sum(), 3),
               "revenue": r((np.array([k["promo_price"] for k in lp_skus]) * s_opt).sum(), 2)},
}
print("LP week", AW[LPW], "budget", BUDGET, "space", SPACE, order_plan["result"])
for k in lp_skus:
    print(f"  {k['cat']:13s} {k['name'][:40]:40s} F {k['forecast']:4d} act {k['actual']:4d} reg {k['reg_price']:.2f} promo {k['promo_price']:.2f} "
          f"m {k['margin']:.2f} pack {k['pack']} min {k['min_cases']} opt {k['opt_cases']} sold {k['opt_sold']} naive {k['naive_cases']}")

# ================================================================== 4. TABLEAU EXTRACT (SKU-week)
TOP_SKUS = 25
STATE = {0: "Ordinary week", 1: "Mailer week", 2: "Price cut continues", 3: "Post-promo week"}
recs = []
crow = {c["cat"]: c for c in cat_rows}
for cat, s in store.items():
    clabel, sec = CATS[cat]
    u, b, P, v, d = s["u"], s["b"], s["P"], s["v"], s["d"]
    state = np.where(s["mail"], 1, np.where(s["ext"], 2, np.where(s["post"], 3, 0)))
    lift_u = np.where(P, u - b, 0)
    dip_u = np.where(s["post"], b - u, 0)
    rank = np.argsort(-u.sum(1), kind="stable")
    top_i, rest_i = rank[:TOP_SKUS], rank[TOP_SKUS:]
    can_rate = max(crow[cat]["cannib_rate"], 0)
    for w in range(NW):
        common = {"week": int(AW[w]), "week_start": str(week_start.iloc[w].date()), "section": sec, "category": clabel,
                  "cat_cannib_rate": can_rate, "cat_net_pct": crow[cat]["net_pct"]}
        for rk, i in enumerate(top_i, 1):
            recs.append({**common, "sku_id": str(s["ids"][i]), "sku_name": label(s["ids"][i]),
                         "brand": str(meta.loc[s["ids"][i], "brand"]), "sku_rank": rk, "row_type": "SKU",
                         "promo_state": STATE[int(state[i, w])], "on_promo": int(P[i, w]),
                         "mailer_share": round(float(s["ms"][i, w]), 2), "display_share": round(float(s["ds"][i, w]), 2),
                         "skus_in_row": 1, "units": int(u[i, w]), "baseline_units": round(float(b[i, w]), 1),
                         "lift_units": round(float(lift_u[i, w]), 1), "dip_units": round(float(dip_u[i, w]), 1),
                         "sales_usd": round(float(v[i, w]), 2), "discount_usd": round(float(d[i, w]), 2)})
        for flag, nm in [(True, "Other SKUs - on promo"), (False, "Other SKUs - not on promo")]:
            m = rest_i[P[rest_i, w] == flag]
            if len(m) == 0:
                continue
            recs.append({**common, "sku_id": "OTHER-PROMO" if flag else "OTHER", "sku_name": nm, "brand": "Mixed",
                         "sku_rank": None, "row_type": "Rollup", "promo_state": "On promo (mixed)" if flag else "Not on promo (mixed)",
                         "on_promo": int(flag), "mailer_share": None, "display_share": None, "skus_in_row": int(len(m)),
                         "units": int(u[m, w].sum()), "baseline_units": round(float(b[m, w].sum()), 1),
                         "lift_units": round(float(lift_u[m, w].sum()), 1), "dip_units": round(float(dip_u[m, w].sum()), 1),
                         "sales_usd": round(float(v[m, w].sum()), 2), "discount_usd": round(float(d[m, w].sum()), 2)})
tab = pd.DataFrame(recs)
tab["shelf_value_usd"] = (tab.sales_usd + tab.discount_usd).round(2)
cols = ["week", "week_start", "section", "category", "sku_id", "sku_name", "brand", "sku_rank", "row_type", "skus_in_row",
        "promo_state", "on_promo", "mailer_share", "display_share", "units", "baseline_units", "lift_units", "dip_units",
        "sales_usd", "discount_usd", "shelf_value_usd", "cat_cannib_rate", "cat_net_pct"]
tab = tab[cols]
tab["sku_rank"] = tab.sku_rank.astype("Int64")
os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
tab.to_csv(OUT_CSV, index=False, encoding="utf-8")
# the extract must add back up to the analysis totals
chk = tab.groupby("category").agg(lift=("lift_units", "sum"), dip=("dip_units", "sum"))
for c in cat_rows:
    assert abs(chk.loc[c["label"], "lift"] - c["gross"]) <= 0.05 * NW * 27, (c["label"], chk.loc[c["label"], "lift"], c["gross"])
    assert abs(chk.loc[c["label"], "dip"] - c["dip"]) <= 0.05 * NW * 27, (c["label"], chk.loc[c["label"], "dip"], c["dip"])
print("tableau rows", len(tab), "bytes", os.path.getsize(OUT_CSV))

# ================================================================== 5. STORY: insights + recommendations (numbers filled from the data)
pct = lambda x: f"{100 * x:.0f}%"
and_join = lambda xs: ", ".join(xs[:-1]) + " and " + xs[-1] if len(xs) > 1 else (xs[0] if xs else "none")
usd = lambda x: f"${x:,.2f}"
avg_shelf = shelf_tot[0] / shelf_tot[1]
for c in cat_rows:
    c["disc_per_net_vs_shelf"] = r(c["disc_per_net_unit"] / c["shelf_price"], 3) if c["disc_per_net_unit"] else None
by_cost = sorted(cat_rows, key=lambda c: -(c["disc_per_net_vs_shelf"] or 9))
dear = [c for c in by_cost if c["disc_per_net_vs_shelf"] >= 0.75]
cheap = [c for c in by_cost if c["disc_per_net_vs_shelf"] <= 0.60]
can_sig = [c for c in cat_rows if c["cannib_ci"][0] > 0]
can_top = max(cat_rows, key=lambda c: c["cannib_ci"][0])        # same rule as the example
dips = sorted([c for c in cat_rows if c["dip_pct_base"] > 0.03], key=lambda c: -c["dip_pct_base"])
ext_share = float((ev.ext_wks > 0).mean())
db = {d_["band"]: d_ for d_ in depth_bands}
ex_by = {e["why"]: e for e in examples}
lp = order_plan["result"]
totals.update({"gross_pct": r(T["gross"] / T["base_in_promo"], 3), "avg_shelf_price": r(avg_shelf, 2),
               "disc_per_net_vs_shelf": r(totals["disc_per_net_unit"] / avg_shelf, 3), "ext_event_share": r(ext_share, 3)})

pp = {k: get_pair(*k) for k in [("DRY NOODLES/PASTA", "PASTA SAUCE"), ("PASTA SAUCE", "FROZEN BREAD/DOUGH"),
                                ("CHEESES", "DELI MEATS"), ("HOT DOGS", "BAKED BREAD/BUNS/ROLLS"), ("BEEF", "BAKED BREAD/BUNS/ROLLS"),
                                ("COLD CEREAL", "FLUID MILK PRODUCTS"), ("SALAD MIX", "SALD DRSNG/SNDWCH SPRD"),
                                ("BACON", "EGGS")]}
P_ = lambda a, b: pp[(a, b)]

insights = [
    {"id": "volume", "head": f"Promotions do move volume: +{pct(totals['gross_pct'])} on the promoted SKU",
     "body": f"Across {totals['events']:,} promotions in the 12 largest food categories, promoted SKUs sold {totals['gross']:,} more units "
             f"than their own baseline: {pct(totals['gross_pct'])} above what they normally sell in those weeks.",
     "nums": {"gross": totals["gross"], "gross_pct": totals["gross_pct"], "events": totals["events"]}},
    {"id": "net", "head": f"{pct(totals['net_pct'])} of the bump is new to the category in the short run",
     "body": f"After taking out units borrowed from sister SKUs ({totals['cannib']:,}) and the post-promotion dip, {totals['net']:,} extra units remain. "
             f"Short-run cannibalisation is small in most categories; the post-promotion dip is close to zero at chain level.",
     "nums": {"net": totals["net"], "net_pct": totals["net_pct"], "cannib": totals["cannib"], "dip": totals["dip"]}},
    {"id": "cannib", "head": f"{can_top['label']} is the clearest exception: about {pct(can_top['cannib_rate'])} of the bump is cannibalised",
     "body": f"When a {can_top['label'].lower()} SKU is in the mailer, the rest of the {can_top['label'].lower()} shelf sells less: roughly "
             f"{pct(can_top['cannib_rate'])} of the extra units (95% range {pct(can_top['cannib_ci'][0])}–{pct(can_top['cannib_ci'][1])}) come out of other SKUs. "
             f"In the example ({ex_by['cannibalisation']['name']}), its mailer weeks pull the rest of the shelf down to "
             f"{pct(ex_by['cannibalisation']['summary']['rest_idx_mailer'])} of its baseline."
             + "".join(f" {c['label']} shows {pct(c['cannib_rate'])} too, but the range is wide ({pct(c['cannib_ci'][0])}–{pct(c['cannib_ci'][1])})."
                       for c in can_sig if c is not can_top and c["cannib_rate"] >= 0.10),
     "nums": {"cat": can_top["label"], "rate": can_top["cannib_rate"], "ci": can_top["cannib_ci"]}},
    {"id": "subsidy", "head": f"The hidden cost: {pct(totals['subsidised_share'])} of promo units would have sold anyway",
     "body": f"Of {totals['promo_units']:,} units sold on promotion, {totals['base_in_promo']:,} were baseline sales that got the discount too. "
             f"Every net extra unit cost {usd(totals['disc_per_net_unit'])} in discounts, {pct(totals['disc_per_net_vs_shelf'])} of the average shelf price ({usd(avg_shelf)}).",
     "nums": {"subsidised_share": totals["subsidised_share"], "disc_per_net_unit": totals["disc_per_net_unit"], "avg_shelf_price": r(avg_shelf, 2)}},
    {"id": "efficiency", "head": f"Extra units cost the most in {by_cost[0]['label'].lower()}, the least in {by_cost[-1]['label'].lower()}",
     "body": f"{by_cost[0]['label']}: {usd(by_cost[0]['disc_per_net_unit'])} of discount per extra unit against a {usd(by_cost[0]['shelf_price'])} shelf price "
             f"({pct(by_cost[0]['disc_per_net_vs_shelf'])}). {by_cost[-1]['label']}: {usd(by_cost[-1]['disc_per_net_unit'])} against {usd(by_cost[-1]['shelf_price'])} "
             f"({pct(by_cost[-1]['disc_per_net_vs_shelf'])}).",
     "nums": {"ranking": [[c["label"], c["disc_per_net_vs_shelf"]] for c in by_cost]}},
    {"id": "depth", "head": "Depth drives lift, and not in a straight line",
     "body": f"Promotions under 20% off lifted the SKU +{pct(db['under 20%']['lift_pct'])}; 30–40% off, +{pct(db['30-40%']['lift_pct'])}; "
             f"40–50% off, +{pct(db['40-50%']['lift_pct'])}. The step past 40% is where shoppers react most.",
     "nums": {"bands": [[d_["band"], d_["lift_pct"], d_["events"]] for d_ in depth_bands]}},
    {"id": "carryover", "head": f"The price cut outlasts the mailer in {pct(ext_share)} of promotions",
     "body": f"The loyalty-card price often runs 1–2 weeks after the mailer week. Those extra weeks carry {totals['gross_ext']:,} of the "
             f"{totals['gross']:,} extra units ({pct(totals['gross_ext'] / totals['gross'])}), which an order plan built on the mailer week alone misses.",
     "nums": {"ext_event_share": r(ext_share, 3), "gross_ext": totals["gross_ext"]}},
    {"id": "dip", "head": "Pantry loading is small, but real in a few places",
     "body": ("The 2 weeks after a promotion sit close to baseline in most categories. The clearest dips: "
              + ", ".join(f"{c['label'].lower()} {pct(c['dip_pct_base'])} below baseline" for c in dips[:3])
              + f". Single SKUs can drop much more: the {ex_by['dip']['name'].split(' · ')[0].lower()} example sold "
              + f"{pct(ex_by['dip']['summary']['dip_pct'])} below baseline in the 2 weeks after its promotions."),
     "nums": {"dips": [[c["label"], c["dip_pct_base"]] for c in dips]}},
    {"id": "display", "head": "Display support showed no extra lift once depth is matched",
     "body": ("Comparing promotions with the same discount depth, the ones with an in-store display did not lift more ("
              + "; ".join(f"{d_['band']} off: +{pct(d_['with_display'])} with display vs +{pct(d_['mailer_only'])} mailer only" for d_ in disp_by_band)
              + "). Displays probably go to weaker items, so this needs a store-split test, not a conclusion."),
     "nums": {"by_band": disp_by_band}},
    {"id": "basket", "head": f"What sells together: pasta and sauce, {pct(P_('DRY NOODLES/PASTA', 'PASTA SAUCE').conf_ab)} of the time",
     "body": f"{pct(P_('DRY NOODLES/PASTA', 'PASTA SAUCE').conf_ab)} of baskets with pasta also have pasta sauce, "
             f"{P_('DRY NOODLES/PASTA', 'PASTA SAUCE').lift:.1f}x more often than chance. Cereal shoppers take milk "
             f"({pct(P_('COLD CEREAL', 'FLUID MILK PRODUCTS').conf_ab)} of cereal baskets) and hot-dog shoppers take buns "
             f"({pct(P_('HOT DOGS', 'BAKED BREAD/BUNS/ROLLS').conf_ab)}).",
     "nums": {"pasta_sauce_conf": r(P_('DRY NOODLES/PASTA', 'PASTA SAUCE').conf_ab, 3), "pasta_sauce_lift": r(P_('DRY NOODLES/PASTA', 'PASTA SAUCE').lift, 2)}},
]

recommendations = [
    {"id": "rank", "head": "Judge promotions by discount per net extra unit, not by lift",
     "body": f"At a typical ~30% grocery margin, a promotion only pays on its own if an extra unit costs less than ~30% of its shelf price in discount. "
             f"All 12 categories are above that line ({pct(by_cost[-1]['disc_per_net_vs_shelf'])}–{pct(by_cost[0]['disc_per_net_vs_shelf'])}), so each one has to earn "
             f"supplier funding or extra store traffic. Shift mailer slots away from categories at {pct(0.75)}+ "
             f"({and_join([c['label'].lower() for c in dear])}) towards those at or under {pct(0.60)} ({and_join([c['label'].lower() for c in cheap])}).",
     "nums": {"dear": [c["label"] for c in dear], "cheap": [c["label"] for c in cheap]}},
    {"id": "depth", "head": "Make 30–40% the default depth; keep 40%+ for vendor-funded traffic drivers",
     "body": f"30–40% off already lifts +{pct(db['30-40%']['lift_pct'])}. Going deeper adds volume fast, but every baseline unit sold in that week gets the deeper discount too.",
     "nums": {"lift_30_40": db["30-40%"]["lift_pct"], "lift_40_50": db["40-50%"]["lift_pct"]}},
    {"id": "orders", "head": "Order for the whole promotion, not just the mailer week",
     "body": f"In {pct(ext_share)} of promotions the price cut keeps going for 1–2 weeks. Carry the lift into the order forecast for those weeks, "
             f"or the shelf runs empty while the price is still low.",
     "nums": {"ext_event_share": r(ext_share, 3)}},
    {"id": "solver", "head": "Plan promo orders with an optimiser when budget or space is tight",
     "body": f"For the July 4th mailer (week {order_plan['week']}), the Solver plan earns {usd(lp['objective'])} from the same "
             f"{usd(order_plan['budget'])} budget and {order_plan['space']:.0f} ft³ of space, against {usd(lp['naive_objective'])} for the usual rule of thumb "
             f"(cut every SKU by the same %, then top up the biggest gaps): +{pct(lp['uplift_vs_naive'] / lp['naive_objective'])}, "
             f"with {pct(lp['fill_rate'])} of forecast demand filled instead of {pct(lp['naive_fill_rate'])}.",
     "nums": {"objective": lp["objective"], "naive": lp["naive_objective"], "fill": lp["fill_rate"], "naive_fill": lp["naive_fill_rate"]}},
    {"id": "milk", "head": f"In {can_top['label'].lower()}, measure the category, not the SKU",
     "body": f"About {pct(can_top['cannib_rate'])} of a {can_top['label'].lower()} promotion's bump comes from sister SKUs. Avoid featuring two near-identical "
             f"SKUs in the same week and report category units, not SKU lift.",
     "nums": {"rate": can_top["cannib_rate"]}},
    {"id": "display", "head": "Test displays before paying for more of them",
     "body": "Run a store-split test (half the stores get the end-cap, half don't, same price) for a few big promotions before buying more display space.",
     "nums": {}},
]

ps, pf = P_("DRY NOODLES/PASTA", "PASTA SAUCE"), P_("PASTA SAUCE", "FROZEN BREAD/DOUGH")
dc, hb, bb = P_("CHEESES", "DELI MEATS"), P_("HOT DOGS", "BAKED BREAD/BUNS/ROLLS"), P_("BEEF", "BAKED BREAD/BUNS/ROLLS")
cm, sd = P_("COLD CEREAL", "FLUID MILK PRODUCTS"), P_("SALAD MIX", "SALD DRSNG/SNDWCH SPRD")
merch = [
    {"id": "pasta", "head": "Pasta night: feature the pasta, let the sauce follow",
     "body": f"{pct(ps.conf_ab)} of pasta baskets include sauce (lift {ps.lift:.1f}, {int(ps.n):,} baskets). Put the mailer discount on pasta only, "
             f"keep sauce at full price on a secondary display in the pasta aisle, and add frozen garlic bread nearby: "
             f"{pct(pf.conf_ab)} of sauce baskets also have frozen bread or dough (lift {pf.lift:.1f}).",
     "pairs": [pair_row(ps), pair_row(pf)]},
    {"id": "deli", "head": "Deli counter: sell meat and cheese as a pair",
     "body": f"{pct(dc.conf_ab)} of baskets with deli cheese also have deli meat (lift {dc.lift:.1f}; still {dc.lift_adj:.1f} after allowing for basket size). "
             f"A 'pick two' slice offer at the counter rewards a habit that already exists.",
     "pairs": [pair_row(dc)]},
    {"id": "cookout", "head": "Cookout weeks: buns follow hot dogs and burgers",
     "body": f"{pct(hb.conf_ab)} of hot-dog baskets and {pct(bb.conf_ab)} of beef baskets include bread or buns. When hot dogs or ground beef are in the mailer, "
             f"raise the bun order and place buns next to the meat case.",
     "pairs": [pair_row(hb), pair_row(bb)]},
    {"id": "breakfast", "head": "Cereal brings milk shoppers: use it, don't double-discount it",
     "body": f"{pct(cm.conf_ab)} of cereal baskets contain milk (lift {cm.lift:.1f}). A cereal promotion already pulls milk at full price, "
             f"so avoid running milk and cereal deals in the same week.",
     "pairs": [pair_row(cm)]},
    {"id": "salad", "head": "Dressing belongs in produce",
     "body": f"{pct(sd.conf_ab)} of salad-mix baskets include dressing (lift {sd.lift:.1f}). A small dressing chiller next to the bagged salads "
             f"captures the shoppers who forget to walk to the dressing aisle.",
     "pairs": [pair_row(sd)]},
]

# ================================================================== 6. WRITE
weekly = {}
for cat, s in store.items():
    u, b, P = s["u"], s["b"], s["P"]
    weekly[CATS[cat][0]] = {"units": [int(x) for x in u.sum(0)], "base": [r(x, 0) for x in b.sum(0)],
                            "promo_units": [int(x) for x in np.where(P, u, 0).sum(0)],
                            "lift": [r(x, 0) for x in np.where(P, u - b, 0).sum(0)]}
for c in cat_rows:
    c.pop("cat")
out = {
    "source": {"name": "84.51° The Complete Journey (2017)", "url": "https://www.8451.com/area51/",
               "pkg": "https://github.com/bradleyboehmke/completejourney", "households": N_HH, "lines": N_LINES,
               "baskets": N_BASKETS, "basket_weeks": [int(WEEKS[0]), int(WEEKS[-1])],
               "weeks": [int(w) for w in AW], "week_start": [str(x.date()) for x in week_start],
               "note": "Weekly series cover weeks 2-52 (Jan 2 - Dec 24, 2017); week 1 is a single day (Jan 1) and is left out of the promotion analysis. Baskets use weeks 1-52."},
    "promo": {
        "rules": {"mail_threshold": MAIL_T, "display_threshold": DISP_T, "ext_pp": EXT_PP, "ext_max_wks": EXT_MAX,
                  "post_wks": POST_WKS, "baseline_window": BASE_WIN[0], "min_weeks_sold": MIN_WEEKS_SOLD,
                  "min_ordinary_wks": MIN_NORMAL_WKS, "life_wks": LIFE_WKS},
        "method": [
            "Promotion week: the SKU is in the mailer at 25% or more of the stores that carry it (same rule as the order recommender).",
            "The promotion continues for up to 2 more weeks while the loyalty-card discount stays at least 5 points deeper than the SKU's usual discount.",
            "Baseline: the SKU's average units in its ordinary weeks (no promotion, not in the 2 weeks after one) within 6 weeks either side, so it follows trend and season.",
            "Gross lift: units above baseline on the promoted SKU during the promotion.",
            "Post-promotion dip: units below baseline in the 2 weeks after (a negative dip means sales stayed above baseline).",
            "Cannibalisation: across the 52 weeks, how far the category's non-promoted SKUs fall below their own baselines for each extra promoted unit, "
            "allowing for store traffic and their own price cuts. A negative estimate (a halo) is shown but never credited.",
            "Net incremental units = gross lift - cannibalisation - post-promotion dip.",
            "Scope: SKUs on sale all year (first sale in weeks 2-7, last in weeks 47-52) with 20+ selling weeks and 8+ ordinary weeks. "
            "Weeks 2-52: week 1 is a single day (Jan 1).",
        ],
        "limits": [
            "Observational data, not an experiment: promotions are not assigned at random, and promo weeks can coincide with holidays or seasons. Local baselines and the traffic control reduce this but don't remove it.",
            "A panel of about 2,500 households, not total store sales: small SKUs are noisy, so results are reported at category level.",
            "Cannibalisation is measured inside the category and the same week. Switching to other categories (soda to juice), to other stores, or stock-piling longer than 2 weeks is not captured.",
            "'Units' mix pack sizes: a 12-pack and a 2-litre bottle each count as one.",
            "Discount per net extra unit is a cost proxy: supplier funding of the discount is not in the data.",
            f"Cannibalisation estimates for single categories are uncertain (see the 95% ranges); only {and_join([c['label'].lower() for c in can_sig])} "
            f"{'are' if len(can_sig) > 1 else 'is'} clearly above zero.",
        ],
        "categories": cat_rows, "totals": totals, "depth_bands": depth_bands,
        "display": {"overall": disp_eff, "by_depth": disp_by_band}, "weekly": weekly, "examples": examples,
    },
    "basket": {
        "n_baskets": N_BASKETS, "min_cat_share": MIN_CAT_SHARE, "min_support": MIN_PAIR_SUPPORT,
        "method": [
            "Each basket is reduced to the set of product categories in it (merchandise only, weeks 1-52).",
            "Support = share of all baskets containing both categories; confidence(A->B) = share of A's baskets that also contain B; lift = how many times more often they appear together than if independent.",
            "lift_adj compares with what independence predicts inside baskets of the same size, so pairs that only co-occur because both turn up in big weekly shops drop towards 1.",
            f"Categories in fewer than {pct(MIN_CAT_SHARE)} of baskets and pairs with support under {MIN_PAIR_SUPPORT:.1%} are left out.",
        ],
        "categories": cat_tbl,
        "pairs": [pair_row(p) for _, p in top.iterrows()],
        "network": network,
        "recommendations": merch,
    },
    "order_plan": order_plan,
    "insights": insights,
    "recommendations": recommendations,
    "downloads": {"solver_xlsx": "downloads/promo_order_optimizer.xlsx", "tableau_csv": "downloads/tableau/promo_performance.csv",
                  "tableau_guide": "downloads/tableau/TABLEAU_BUILD_GUIDE.md"},
}
os.makedirs(os.path.dirname(OUT_JS), exist_ok=True)
with open(OUT_JS, "w", encoding="utf-8") as fh:
    fh.write("/* generated by analysis/retail_promo_basket.py — do not edit by hand. Schema: analysis/RETAIL_EXTRA_SCHEMA.md */\n")
    fh.write("window.DATA_RETAIL_EXTRA = " + json.dumps(out, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + ";\n")
print("wrote", OUT_JS, os.path.getsize(OUT_JS), "bytes")
for i_ in insights + recommendations + merch:
    print("-", i_["head"], "|", i_["body"])
