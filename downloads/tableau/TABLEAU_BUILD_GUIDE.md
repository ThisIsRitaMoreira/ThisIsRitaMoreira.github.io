# Promo performance dashboard: Tableau Public build guide

This guide builds a one-page dashboard from `promo_performance.csv`, in about an hour.

**The question it answers:** *Do our mailer promotions create new sales, or do they mostly give a discount on units we would have sold anyway?*

**The story it tells, top to bottom:**

1. Promotions lift the promoted SKU by +140% on average.
2. About 91% of that bump is still extra category volume once cannibalisation and the post-promo dip are taken out.
3. But 42% of the units sold on promotion would have sold anyway, at full price. Each net extra unit costs $1.90 in discount, 80% of the average shelf price.
4. The cost varies a lot by category, and deeper discounts buy disproportionately more lift.

Data: 84.51° *The Complete Journey*, 2017 (2,469 households). The 12 largest food categories, weeks 2–52 (week 1 is a single day). Built by `analysis/retail_promo_basket.py`.

---

## 1. The file

`promo_performance.csv` has 16,499 rows and 2.6 MB. **One row = one SKU in one week.** Each category has its top 25 SKUs as separate rows. All the other SKUs in the category are rolled up into two rows per week: `Other SKUs - on promo` and `Other SKUs - not on promo`. Summing over all rows therefore gives exact category totals.

| Column | Type | Meaning |
|---|---|---|
| `week` | whole number | Week of 2017 (2–52) |
| `week_start` | date | Monday the week starts |
| `section` | text | Store section: Dairy, Drinks, Bakery, Frozen, Meat & deli, Pantry & snacks |
| `category` | text | One of the 12 categories (e.g. *Soft drinks*, *Milk*) |
| `sku_id`, `sku_name`, `brand` | text | Product. Brand is *National* or *Private* (own brand). Roll-ups use `OTHER` / `OTHER-PROMO` and brand *Mixed* |
| `sku_rank` | whole number | 1–25, rank by units inside the category. Empty for roll-ups |
| `row_type` | text | `SKU` or `Rollup` |
| `skus_in_row` | whole number | 1 for a SKU, otherwise how many SKUs the roll-up holds that week |
| `promo_state` | text | `Mailer week`, `Price cut continues` (the loyalty price ran on after the mailer), `Post-promo week` (the 2 weeks after), `Ordinary week`. Roll-ups: `On promo (mixed)` / `Not on promo (mixed)` |
| `on_promo` | 0/1 | 1 in mailer weeks and price-cut-continues weeks |
| `mailer_share`, `display_share` | 0–1 | Share of the stores carrying the SKU that featured it in the mailer / on an in-store display (empty for roll-ups) |
| `units` | number | Units sold |
| `baseline_units` | number | What the SKU normally sells in that part of the year (ordinary weeks within ±6 weeks) |
| `lift_units` | number | `units − baseline` in promo weeks, otherwise 0 (**gross lift**) |
| `dip_units` | number | `baseline − units` in post-promo weeks, otherwise 0 (**post-promo dip**; negative = sales stayed above baseline) |
| `sales_usd` | number | What shoppers paid |
| `discount_usd` | number | Loyalty-card discount given |
| `shelf_value_usd` | number | `sales + discount`, i.e. value at shelf price |
| `cat_cannib_rate` | 0–1 | Category cannibalisation rate (share of the gross lift taken from sister SKUs). Constant within a category; 0 where no cannibalisation was found |
| `cat_net_pct` | number | The analysis' net-as-%-of-gross for the category, kept for checking |

---

## 2. Connect

1. Open **Tableau Public** (desktop app) > **Connect > To a File > Text file** > choose `promo_performance.csv`.
2. On the Data Source tab, check the types:
   * `week_start` → **Date**
   * `week`, `on_promo`, `sku_rank` → **Number (whole)**
   * `sku_id` → **String** (click the `#` icon and change it, so it isn't summed)
3. Tableau shows `lift_units` as **Lift Units**, `cat_cannib_rate` as **Cat Cannib Rate**, and so on. The formulas below use those names.

---

## 3. Calculated fields

Create these under **Analysis > Create Calculated Field**. Row-level fields (no `SUM`) come first, then the ratios built from them.

```text
// --- row level -------------------------------------------------------
Cannibalised Units      = [Lift Units] * [Cat Cannib Rate]
Promo Units             = IF [On Promo] = 1 THEN [Units] END
Baseline in Promo       = IF [On Promo] = 1 THEN [Baseline Units] END
Promo Discount $        = IF [On Promo] = 1 THEN [Discount Usd] END
Promo Shelf Value $     = IF [On Promo] = 1 THEN [Shelf Value Usd] END

// --- aggregates --------------------------------------------------------
Net Incremental Units   = SUM([Lift Units]) - SUM([Cannibalised Units]) - SUM([Dip Units])
Net % of Gross          = [Net Incremental Units] / SUM([Lift Units])
Promo Lift %            = SUM([Lift Units]) / SUM([Baseline in Promo])
Promo Share of Units    = SUM([Promo Units]) / SUM([Units])
Sold Anyway %           = SUM([Baseline in Promo]) / SUM([Promo Units])
Promo Discount %        = SUM([Promo Discount $]) / SUM([Promo Shelf Value $])
Discount per Net Unit   = SUM([Promo Discount $]) / [Net Incremental Units]
Shelf Price (ordinary)  = SUM(IF [Promo State] = "Ordinary week" THEN [Shelf Value Usd] END)
                        / SUM(IF [Promo State] = "Ordinary week" THEN [Units] END)
Cost per Net Unit vs Shelf = [Discount per Net Unit] / [Shelf Price (ordinary)]

// --- SKU-level discount depth, for the scatter and the depth bands --------
SKU Promo Depth         = { FIXED [Category], [Sku Id] :
                            SUM([Promo Discount $]) / SUM([Promo Shelf Value $]) }
```

Formatting: set the `%` fields to *Percentage, 0 decimals* and `Discount per Net Unit` to *Currency, 2 decimals* (right-click > Default Properties > Number Format).

Then make a **bin** on `SKU Promo Depth`: right-click > Create > Bins, size `0.1`. Name it **Depth Band**.

> `Shelf Price (ordinary)` only counts the top-25 SKU rows in ordinary weeks, because roll-up rows mix weeks of different kinds. It approximates the category's regular price. Use it only as the denominator for `Cost per Net Unit vs Shelf`.

---

## 4. The four sheets

### Sheet 1 · "Where the promo units come from" (category scorecard)

* **Rows:** `Category`, sorted by `Net Incremental Units` descending.
* **Columns:** `Measure Values`. **Filters:** `Measure Names` = *Lift Units (SUM)*, *Cannibalised Units (SUM)*, *Dip Units (SUM)*, *Net Incremental Units*.
* **Marks:** Bar. **Colour:** `Measure Names` (gross = dark blue, cannibalised = orange, dip = grey, net = green). Put `Measure Names` on **Columns** too, so the four bars sit side by side for each category.
* **Tooltip:** add `Net % of Gross`, `Sold Anyway %`, `Discount per Net Unit`, `Promo Discount %`.
* Title: *Gross lift, what it borrows, and what's left*.

*Alternative if space is tight:* a single bar of `Cost per Net Unit vs Shelf` per category, with a reference line at 0.30 (the margin line, see the story below).

### Sheet 2 · "Weekly units: baseline vs promo" (trend)

* **Columns:** `Week Start` (exact date, continuous, *Week* level).
* **Rows:** `SUM(Units)` as bars, plus `SUM(Baseline Units)` on a dual axis as a line. **Synchronise axes.**
* **Colour (bars):** `Promo State`. Suggested palette: *Mailer week* dark blue, *Price cut continues* mid blue, *Post-promo week* amber, *Ordinary week* light grey, roll-ups the same family.
* **Filter:** `Category` → *Show Filter*, *Single Value (dropdown)*. Default: *Milk*.
* Read it: the blue spikes sit above the baseline line. The amber weeks after them should dip below it if shoppers stock up. Mostly they don't.

### Sheet 3 · "Deeper discounts, bigger lift" (scatter)

* **Filter:** `Row Type` = *SKU*, and `Promo Units` > 0. Use the SUM, so only SKUs that were ever promoted show.
* **Columns:** `Promo Discount %`. **Rows:** `Promo Lift %`.
* **Detail:** `Sku Id`, `Sku Name`. **Colour:** `Category`. **Size:** `SUM(Promo Units)`.
* Analytics pane: add a **Trend Line** (polynomial, degree 2), or simply a *Reference Band* from 0.30 to 0.40 on the x-axis labelled "default depth".
* Optional companion bar: `Depth Band` on Columns, `Promo Lift %` on Rows. It shows the step past 40% off.

### Sheet 4 · "One SKU, week by week" (timeline)

* Same build as Sheet 2, but filtered to one SKU: **Filter** `Row Type` = *SKU*; put `Sku Name` on the **Detail** shelf.
* **Columns:** `Week Start`; **Rows:** `SUM(Units)` bars coloured by `Promo State`, plus `SUM(Baseline Units)` as a line.
* This sheet is driven by a click on Sheet 3 (see Actions). Until then, show the title *Click a SKU in the scatter*.

### KPI tiles (four small sheets, "BANs")

Each is a sheet with a single measure on **Text**, font size 28, with a label underneath:

| Tile | Measure | What you should see (all categories) |
|---|---|---|
| Promo lift on the promoted SKU | `Promo Lift %` | **+140%** |
| Net new to the category | `Net % of Gross` | **91%** |
| Would have sold anyway | `Sold Anyway %` | **42%** |
| Discount per net extra unit | `Discount per Net Unit` | **$1.90** |

---

## 5. Dashboard

**Size:** *Fixed*, 1200 × 1000 px (Tableau Public's gallery thumbnails like this ratio).

**Layout (top to bottom):**

```
┌───────────────────────────────────────────────────────────────────────┐
│ Title: "Do our promotions create sales, or just discount them?"       │
│ Subtitle: 12 food categories · 2017 · 84.51° Complete Journey         │
├──────────────┬──────────────┬──────────────┬──────────────────────────┤
│ +140% lift   │ 91% net new  │ 42% sold     │ $1.90 discount per       │
│              │              │ anyway       │ net extra unit           │
├──────────────────────────────────┬────────────────────────────────────┤
│ Sheet 1 · category scorecard     │ Sheet 3 · discount depth vs lift   │
│ (bars)                           │ (scatter)                          │
├──────────────────────────────────┴────────────────────────────────────┤
│ Sheet 2 · weekly units vs baseline for the selected category          │
├───────────────────────────────────────────────────────────────────────┤
│ Sheet 4 · selected SKU, week by week                                  │
├───────────────────────────────────────────────────────────────────────┤
│ Notes: method + limits (small text)                                   │
└───────────────────────────────────────────────────────────────────────┘
```

Use a **Horizontal** container for the KPI row and another for Sheets 1 and 3. Drop the sheets in, then remove their titles where the tile label already says it.

**Filters and actions (Dashboard > Actions > Add Action):**

1. **Filter action "Pick a category":** source Sheet 1, target Sheets 2 and 3, run on *Select*, field `Category`. Clearing the selection shows all values.
2. **Filter action "Pick a SKU":** source Sheet 3, target Sheet 4, run on *Select*, fields `Sku Id`. Clearing the selection excludes all values (so Sheet 4 waits for a click).
3. **Section filter:** show `Section` as a dropdown and apply it to *All Using This Data Source*.
4. Optional **highlight action** on `Promo State` from the legend.

**Notes box (bottom, small grey text).** Paste:

> *Promotion = SKU in the mailer at ≥25% of the stores carrying it, extended while the loyalty price stays ≥5 pts deeper than usual (up to 2 weeks). Baseline = the SKU's ordinary weeks within ±6 weeks. Cannibalisation = how far non-promoted SKUs in the same category fall below their baseline per extra promoted unit (regression over the weeks, controlling for store traffic and their own price cuts); a negative estimate (halo) is not credited. Net = gross − cannibalised − dip. Observational data, not an experiment; a household panel, not total store sales.*

---

## 6. Check your numbers

If your sheets match these, the calculations are right.

| Category | Gross lift | Cannibalised | Dip | Net | Net % | Sold anyway | Promo depth | $ per net unit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Soft drinks | 21,468 | 1,739 | 164 | 19,565 | 91% | 33% | 39% | $2.18 |
| Beef | 9,308 | 316 | 256 | 8,736 | 94% | 32% | 31% | $3.13 |
| Milk | 21,594 | 4,470 | −904 | 18,028 | 83% | 28% | 36% | $1.23 |
| Cheese | 8,038 | 177 | 81 | 7,780 | 97% | 52% | 33% | $1.66 |
| Frozen meals | 7,326 | 0 | 244 | 7,082 | 97% | 48% | 37% | $1.92 |
| Bagged snacks | 1,386 | 0 | −161 | 1,547 | 112% | 61% | 25% | $1.58 |
| Bread & rolls | 3,433 | 663 | −98 | 2,868 | 84% | 68% | 32% | $1.70 |
| Frozen pizza | 5,389 | 0 | 40 | 5,349 | 99% | 46% | 28% | $1.55 |
| Cold cereal | 3,362 | 683 | 197 | 2,483 | 74% | 36% | 38% | $2.67 |
| Lunchmeat | 4,397 | 0 | 39 | 4,358 | 99% | 33% | 40% | $1.66 |
| Ice cream | 3,631 | 0 | 227 | 3,405 | 94% | 30% | 47% | $2.93 |
| Yogurt | 3,417 | 0 | −51 | 3,469 | 102% | 68% | 30% | $0.74 |
| **All 12** | **92,750** | **8,047** | **33** | **84,669** | **91%** | **42%** | **35%** | **$1.90** |

(These can differ from the website's figures by a few units because the CSV rounds each row to 0.1.)

---

## 7. What to say about it (the 30-second version)

* **Promotions work on volume.** Promoted SKUs sell 2.4× their baseline in promo weeks, and in the short run most of that is new to the category. Cannibalisation shows up clearly only in **milk** (~21% of the bump comes from other milk SKUs), and less certainly in bread and soft drinks. Pantry-loading dips are small except **ice cream** and **cereal** (10–13% below baseline in the 2 weeks after).
* **The cost hides in the base.** 42% of promo units would have sold anyway, and they get the discount too. Per *net* extra unit, the chain gives away $1.90, or 80% of the shelf price. At a ~30% grocery margin, no category pays for itself on discount alone: each needs supplier funding or a traffic argument.
* **Where to act.** Relative to shelf price, soft drinks ($2.18 per net unit, more than the $2.08 shelf price), ice cream and cereal are the most expensive ways to buy volume. Milk ($1.23, 52% of shelf price) and beef (60%) are the cheapest. Lift climbs steeply with depth: +32% under 20% off, +140% at 30–40%, +350% at 40–50%. Make 30–40% the default depth, and keep 40%+ for vendor-funded traffic drivers.

## 8. Publish

**File > Save to Tableau Public As…** Name it *Promo performance: what promotions really do*. In the workbook's details on your profile, add the source link (https://www.8451.com/area51/) and a link back to the portfolio page.
