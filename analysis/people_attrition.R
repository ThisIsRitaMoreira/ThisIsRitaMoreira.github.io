# =============================================================================
# people_attrition.R -- "Who leaves, when, and what could we do about it?"
#
# People analytics on the IBM HR Analytics Employee Attrition sample:
# 1,470 FICTIONAL employees created by IBM data scientists (not a real company).
#   https://github.com/IBM/employee-attrition-aif360/blob/master/data/emp_attrition.csv
#
# Author : Rita Moreira
# Usage  : Rscript analysis/people_attrition.R <ibm_attrition.csv> <out_dir>
# Output : <out_dir>/attrition.js, which sets window.DATA_ATTRITION = {...}
#          (the site loads it as a <script>, so it also works offline).
# Needs  : dplyr, survival, broom, rpart, jsonlite (base R otherwise).
#
# Steps
#   1. Baseline     attrition rate overall and by segment, chi-square per variable
#   2. Logistic     odds ratios + 70/30 stratified hold-out: AUC, calibration,
#                   confusion matrix when the riskiest 20% are flagged
#   3. Survival     Kaplan-Meier retention by overtime and job level, log-rank
#                   tests, Cox proportional-hazards model
#   4. Tree         rpart segmentation -> readable "who leaves" rules
#   5. What-if      expected leavers if overtime were removed for a share of
#                   overtime workers (per-employee counterfactuals for the UI)
#   6. Story        plain-English insights and recommendations built from the numbers
#
# The R Markdown report (analysis/people_attrition.Rmd) runs these SAME chunks
# through knitr::read_chunk() and adds ggplot2 charts and narrative.
# Lines starting with "## ----" are chunk labels for that; R ignores them.
# =============================================================================

## ---- setup ----
suppressWarnings(suppressPackageStartupMessages({   # quiet "built under R x.y" notes
  library(dplyr)
  library(survival)
  library(broom)
  library(rpart)
  library(jsonlite)
}))

# When knitted, the Rmd defines SRC itself; from the command line, read the args.
if (!exists("SRC")) {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) < 2) stop("Usage: Rscript people_attrition.R <ibm_attrition.csv> <out_dir>")
  SRC <- args[1]
  OUT_DIR <- args[2]
}

SEED        <- 2026                      # one seed for the train/test split
TOP_SHARE   <- 0.20                      # "flag the riskiest 20%" for the confusion matrix
OT_SHARES   <- c(0, 0.25, 0.5, 0.75, 1)  # what-if: share of overtime workers taken off overtime
KM_YEARS    <- c(1, 2, 5, 10)            # retention checkpoints
KM_MIN_RISK <- 10                        # fewer people than this at risk in a step = too thin to quote

pct <- function(x, d = 0) paste0(formatC(100 * x, format = "f", digits = d), "%")
num <- function(x) formatC(round(x), format = "d", big.mark = ",")
fmt_p <- function(p) if (p < 0.001) "< 0.001" else sprintf("= %.3f", p)
dash <- "\u2013"                          # en dash, kept as an escape so this file stays ASCII

## ---- load ----
# Read the CSV as plain data (it starts with a UTF-8 byte-order mark).
hr_raw <- read.csv(SRC, fileEncoding = "UTF-8-BOM", stringsAsFactors = FALSE)

expected_cols <- c(
  "Age", "Attrition", "BusinessTravel", "DailyRate", "Department", "DistanceFromHome",
  "Education", "EducationField", "EmployeeCount", "EmployeeNumber", "EnvironmentSatisfaction",
  "Gender", "HourlyRate", "JobInvolvement", "JobLevel", "JobRole", "JobSatisfaction",
  "MaritalStatus", "MonthlyIncome", "MonthlyRate", "NumCompaniesWorked", "Over18", "OverTime",
  "PercentSalaryHike", "PerformanceRating", "RelationshipSatisfaction", "StandardHours",
  "StockOptionLevel", "TotalWorkingYears", "TrainingTimesLastYear", "WorkLifeBalance",
  "YearsAtCompany", "YearsInCurrentRole", "YearsSinceLastPromotion", "YearsWithCurrManager")
missing_cols <- setdiff(expected_cols, names(hr_raw))
if (length(missing_cols)) stop("Missing columns: ", paste(missing_cols, collapse = ", "))
stopifnot(!anyNA(hr_raw[expected_cols]),
          all(hr_raw$Attrition %in% c("Yes", "No")),
          !anyDuplicated(hr_raw$EmployeeNumber))

# Three columns hold a single value for everyone, so they carry no information.
const_cols <- c("EmployeeCount", "Over18", "StandardHours")
stopifnot(all(vapply(hr_raw[const_cols], function(x) length(unique(x)) == 1, logical(1))))

hr <- hr_raw %>%
  select(-all_of(const_cols)) %>%
  mutate(left = as.integer(Attrition == "Yes"))

n_emp        <- nrow(hr)
n_left       <- sum(hr$left)
overall_rate <- n_left / n_emp

## ---- segments ----
# Display versions of each segmenting variable (bands for the continuous ones).
rating_lab <- c("Low", "Medium", "High", "Very High")      # IBM codebook, 1-4 scales
wlb_lab    <- c("Bad", "Good", "Better", "Best")
band <- function(x, breaks, labels) cut(x, breaks = breaks, labels = labels, include.lowest = TRUE)

# Income quartiles, labelled with the actual min-max inside each quartile.
inc_q   <- cut(hr$MonthlyIncome, quantile(hr$MonthlyIncome, 0:4 / 4), include.lowest = TRUE, labels = FALSE)
inc_rng <- tapply(hr$MonthlyIncome, inc_q, range)
inc_lab <- sprintf("Q%d (%s%s%s)", 1:4,
                   vapply(inc_rng, function(r) num(r[1]), ""), dash,
                   vapply(inc_rng, function(r) num(r[2]), ""))

seg_df <- hr %>% transmute(
  left,
  OverTime                = factor(OverTime, levels = c("No", "Yes")),
  JobLevel                = factor(paste("Level", JobLevel)),
  MaritalStatus           = factor(MaritalStatus),
  BusinessTravel          = factor(BusinessTravel,
                                   levels = c("Non-Travel", "Travel_Rarely", "Travel_Frequently"),
                                   labels = c("Non-travel", "Travels rarely", "Travels frequently")),
  Department              = factor(Department),
  JobRole                 = factor(JobRole),
  AgeBand                 = band(Age, c(18, 24, 29, 34, 44, 60),
                                 paste0(c("18", "25", "30", "35", "45"), dash, c("24", "29", "34", "44", "60"))),
  TenureBand              = band(YearsAtCompany, c(0, 1, 4, 9, 40),
                                 c(paste0("0", dash, "1 yrs"), paste0("2", dash, "4 yrs"),
                                   paste0("5", dash, "9 yrs"), "10+ yrs")),
  IncomeBand              = factor(inc_lab[inc_q], levels = inc_lab),
  JobSatisfaction         = factor(JobSatisfaction, 1:4, paste(1:4, rating_lab)),
  EnvironmentSatisfaction = factor(EnvironmentSatisfaction, 1:4, paste(1:4, rating_lab)),
  WorkLifeBalance         = factor(WorkLifeBalance, 1:4, paste(1:4, wlb_lab)),
  StockOptionLevel        = factor(paste("Level", StockOptionLevel)),
  DistanceBand            = band(DistanceFromHome, c(1, 5, 10, 20, 29),
                                 paste0(c("1", "6", "11", "21"), dash, c("5", "10", "20", "29")))
)

seg_spec <- data.frame(
  key   = c("OverTime", "JobLevel", "MaritalStatus", "BusinessTravel", "Department", "JobRole",
            "AgeBand", "TenureBand", "IncomeBand", "JobSatisfaction", "EnvironmentSatisfaction",
            "WorkLifeBalance", "StockOptionLevel", "DistanceBand"),
  label = c("Overtime", "Job level", "Marital status", "Business travel", "Department", "Job role",
            "Age", "Years at company", "Monthly income (quartile)", "Job satisfaction",
            "Environment satisfaction", "Work-life balance", "Stock option level", "Distance from home"),
  kind  = c("nominal", "ordinal", "nominal", "ordinal", "nominal", "nominal",
            "ordinal", "ordinal", "ordinal", "ordinal", "ordinal",
            "ordinal", "ordinal", "ordinal"),
  stringsAsFactors = FALSE)

# Wilson 95% interval for a proportion: honest error bars for small segments.
wilson <- function(x, n, z = 1.96) {
  p <- x / n
  den <- 1 + z^2 / n
  ctr <- (p + z^2 / (2 * n)) / den
  half <- z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2)) / den
  cbind(lo = ctr - half, hi = ctr + half)
}

segment_one <- function(key, label, kind) {
  tab  <- table(seg_df[[key]], seg_df$left)            # rows = levels, cols = stayed/left
  test <- suppressWarnings(chisq.test(tab, correct = FALSE))
  n    <- as.vector(rowSums(tab))
  lv   <- as.vector(tab[, "1"])
  ci   <- wilson(lv, n)
  lev  <- data.frame(level = rownames(tab), n = n, leavers = lv, rate = lv / n,
                     ci_low = ci[, "lo"], ci_high = ci[, "hi"], stringsAsFactors = FALSE)
  lev$lift <- lev$rate / overall_rate
  if (kind == "nominal") lev <- lev[order(-lev$rate), ]  # unordered categories: highest rate first
  list(key = key, label = label, kind = kind,
       chi2 = unname(test$statistic), df = unname(test$parameter), p_value = test$p.value,
       cramers_v = sqrt(unname(test$statistic) / (sum(tab) * (min(dim(tab)) - 1))),
       min_expected = min(test$expected), significant = test$p.value < 0.05,
       levels = lev)
}

segments <- Map(segment_one, seg_spec$key, seg_spec$label, seg_spec$kind)
# Strongest association first (Cramer's V is comparable across variables with different level counts).
segments <- segments[order(-vapply(segments, `[[`, 0, "cramers_v"))]

seg_tests <- bind_rows(lapply(segments, function(s)
  data.frame(variable = s$label, chi2 = s$chi2, df = s$df, p_value = s$p_value,
             cramers_v = s$cramers_v, significant = s$significant)))

# The individual levels with the highest attrition (only groups of 50+ people).
top_levels <- bind_rows(lapply(segments, function(s) cbind(variable = s$label, key = s$key, s$levels))) %>%
  filter(n >= 50) %>%
  arrange(desc(rate)) %>%
  slice_head(n = 10)

## ---- model-data ----
# One interpretable predictor set. Choices:
# * Binary flags read as "this group vs everyone else"; the rest are per-unit slopes.
# * JobLevel is kept (as entry level vs 2+); MonthlyIncome and TotalWorkingYears are
#   left out because they are near-duplicates of it (r = 0.95 and 0.78).
# * YearsInCurrentRole / YearsWithCurrManager duplicate YearsAtCompany (r ~ 0.77).
# * Gender is left out on purpose; age and marital status stay in as controls so the
#   other effects are not confounded, never as levers to act on individuals.
# * Nothing measured after the exit decision is used, so there is no leakage.
model_df <- hr %>% transmute(
  EmployeeNumber,
  left,
  Overtime                   = as.integer(OverTime == "Yes"),
  EntryLevel                 = as.integer(JobLevel == 1),
  NoStockOptions             = as.integer(StockOptionLevel == 0),
  Single                     = as.integer(MaritalStatus == "Single"),
  FrequentTravel             = as.integer(BusinessTravel == "Travel_Frequently"),
  LowJobSatisfaction         = as.integer(JobSatisfaction == 1),
  LowEnvironmentSatisfaction = as.integer(EnvironmentSatisfaction == 1),
  LowJobInvolvement          = as.integer(JobInvolvement == 1),
  PoorWorkLifeBalance        = as.integer(WorkLifeBalance == 1),
  DeptSales                  = as.integer(Department == "Sales"),
  DeptHR                     = as.integer(Department == "Human Resources"),
  Age10                      = Age / 10,
  YearsAtCompany,
  YearsSinceLastPromotion,
  NumCompaniesWorked,
  Distance10                 = DistanceFromHome / 10
)

term_labels <- c(
  Overtime                   = "Works overtime (vs not)",
  EntryLevel                 = "Job level 1 (vs level 2+)",
  NoStockOptions             = "No stock options (vs any)",
  Single                     = "Single (vs married or divorced)",
  FrequentTravel             = "Travels frequently (vs rarely or never)",
  LowJobSatisfaction         = "Low job satisfaction (1 of 4)",
  LowEnvironmentSatisfaction = "Low environment satisfaction (1 of 4)",
  LowJobInvolvement          = "Low job involvement (1 of 4)",
  PoorWorkLifeBalance        = "Poor work-life balance (1 of 4)",
  DeptSales                  = "Sales department (vs R&D)",
  DeptHR                     = "HR department (vs R&D)",
  Age10                      = "Age, per +10 years",
  YearsAtCompany             = "Years at company, per +1",
  YearsSinceLastPromotion    = "Years since last promotion, per +1",
  NumCompaniesWorked         = "Number of prior employers, per +1",
  Distance10                 = "Distance from home, per +10 units"
)
predictors <- names(term_labels)
f_logit <- reformulate(predictors, response = "left")

## ---- split ----
# 70/30 split, stratified on the outcome so both halves keep the 16% attrition rate.
set.seed(SEED)
idx_left <- which(model_df$left == 1)
idx_stay <- which(model_df$left == 0)
train_idx <- sort(c(sample(idx_left, round(0.7 * length(idx_left))),
                    sample(idx_stay, round(0.7 * length(idx_stay)))))
train <- model_df[train_idx, ]
test  <- model_df[-train_idx, ]

## ---- logit ----
# Validate the specification on the hold-out, then refit on everyone for the
# reported odds ratios and the what-if (more data, tighter intervals).
fit_train <- glm(f_logit, family = binomial, data = train)
fit_full  <- glm(f_logit, family = binomial, data = model_df)

or_tab <- suppressMessages(tidy(fit_full, exponentiate = TRUE, conf.int = TRUE)) %>%
  filter(term != "(Intercept)") %>%
  transmute(term, label = unname(term_labels[term]), odds_ratio = estimate,
            ci_low = conf.low, ci_high = conf.high, p_value = p.value,
            significant = p.value < 0.05) %>%
  arrange(desc(odds_ratio))

null_dev <- glm(left ~ 1, family = binomial, data = model_df)
pseudo_r2 <- 1 - as.numeric(logLik(fit_full)) / as.numeric(logLik(null_dev))  # McFadden

## ---- validation ----
# AUC via the rank (Mann-Whitney) formula: the probability that a random leaver
# gets a higher predicted risk than a random stayer. Ties count half via mid-ranks.
auc_mw <- function(p, y) {
  r <- rank(p)
  n1 <- sum(y == 1); n0 <- sum(y == 0)
  (sum(r[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)
}

p_train   <- fitted(fit_train)
p_test    <- predict(fit_train, newdata = test, type = "response")
auc_train <- auc_mw(p_train, train$left)
auc_test  <- auc_mw(p_test, test$left)
brier     <- mean((p_test - test$left)^2)

# Benchmark: what does overtime alone achieve?
fit_ot_only <- glm(left ~ Overtime, family = binomial, data = train)
auc_ot_only <- auc_mw(predict(fit_ot_only, newdata = test, type = "response"), test$left)

# Calibration: within each decile of predicted risk, does the predicted rate match reality?
calib <- data.frame(p = p_test, y = test$left) %>%
  mutate(decile = ntile(p, 10)) %>%
  group_by(decile) %>%
  summarise(n = n(), leavers = sum(y), mean_predicted = mean(p), actual_rate = mean(y),
            p_min = min(p), p_max = max(p), .groups = "drop")

# Confusion matrix when HR flags the riskiest 20% of the hold-out group.
thr  <- unname(quantile(p_test, 1 - TOP_SHARE))
flag <- p_test >= thr
cm <- list(
  threshold = thr, flagged = sum(flag), test_n = nrow(test),
  tp = sum(flag & test$left == 1), fp = sum(flag & test$left == 0),
  fn = sum(!flag & test$left == 1), tn = sum(!flag & test$left == 0))
cm$precision   <- cm$tp / (cm$tp + cm$fp)
cm$recall      <- cm$tp / (cm$tp + cm$fn)
cm$specificity <- cm$tn / (cm$tn + cm$fp)
cm$accuracy    <- (cm$tp + cm$tn) / cm$test_n
cm$base_rate   <- mean(test$left)
cm$lift        <- cm$precision / cm$base_rate

# Gains: flag the top k% by risk -> what share of all leavers is caught?
ord     <- order(p_test, decreasing = TRUE)
y_ord   <- test$left[ord]
gains   <- data.frame(share_flagged = seq(0.05, 1, by = 0.05)) %>%
  mutate(k = ceiling(share_flagged * length(y_ord)),
         leavers_caught = cumsum(y_ord)[k],
         share_of_leavers = leavers_caught / sum(y_ord),
         precision = leavers_caught / k)

# ROC curve, thinned to about 60 points for the browser.
roc_points <- function(p, y, max_pts = 60) {
  cuts <- sort(unique(p), decreasing = TRUE)
  df <- data.frame(fpr = c(0, vapply(cuts, function(t) mean(p[y == 0] >= t), 0)),
                   tpr = c(0, vapply(cuts, function(t) mean(p[y == 1] >= t), 0)))
  df[unique(round(seq(1, nrow(df), length.out = max_pts))), ]
}
roc <- roc_points(p_test, test$left)

## ---- survival ----
# WHEN do people leave? Time = years at company (recorded in whole years).
#
# Why not the textbook Kaplan-Meier? The file is a one-period snapshot: Attrition
# flags people who left during the observation window, and anyone who left in
# earlier years is simply absent. The textbook curve (time = tenure, stayers
# censored) still places every long-tenured stayer in the early-tenure risk sets,
# although nobody could have been seen leaving at that tenure years ago. That is
# left truncation, and it hides early exits: the textbook curve says 99% of hires
# survive year 1 while 36% of first-year employees in the file left.
#
# Fix: delayed entry. Assume the window is one year (the usual reading of this
# data as 16% annual attrition). An employee with k completed years was then at
# risk only from tenure k to k + 1, so each person is Surv(start = k, stop = k + 1).
# The curve is a synthetic cohort: "if this year's exit rates by tenure held, the
# share of new hires still here after t years". Group membership (overtime, job
# level) is measured today and can change over a career.
surv_df <- hr %>% transmute(
  YearsAtCompany,
  start     = YearsAtCompany,
  stop      = YearsAtCompany + 1,
  event     = left,
  OverTime  = factor(OverTime, levels = c("No", "Yes")),
  JobLevel5 = factor(paste("Level", JobLevel)),          # all five levels (textbook view)
  # levels 4 and 5 have 0-6 people per early tenure year, so 3-5 are pooled
  JobLevel  = factor(ifelse(JobLevel >= 3, paste0("Level 3", dash, "5"), paste("Level", JobLevel))))

km_all <- survfit(Surv(start, stop, event) ~ 1,        data = surv_df)
km_ot  <- survfit(Surv(start, stop, event) ~ OverTime, data = surv_df)
km_jl  <- survfit(Surv(start, stop, event) ~ JobLevel, data = surv_df)

# survdiff() has no delayed-entry form. The Cox score test with one group factor
# is the log-rank test generalised to (start, stop] data.
score_test <- function(var) {
  s <- summary(coxph(as.formula(paste("Surv(start, stop, event) ~", var)), data = surv_df))$sctest
  list(method = "log-rank (Cox score test, delayed entry)",
       chi2 = unname(s["test"]), df = unname(s["df"]), p_value = unname(s["pvalue"]))
}
logrank <- function(sd) {                        # classic survdiff, for the textbook view
  df <- length(sd$n) - 1
  list(method = "log-rank (survdiff, no delayed entry)",
       chi2 = unname(sd$chisq), df = df, p_value = pchisq(sd$chisq, df, lower.tail = FALSE))
}

# Tidy each stratum of a survfit: step points, retention checkpoints, median, and
# how many people stand behind each estimate (risk sets are small at some tenures).
km_groups <- function(fit, data, var = NULL) {
  groups <- if (is.null(var)) "All employees" else levels(data[[var]])
  grp <- if (is.null(fit$strata)) rep(groups, length(fit$time)) else rep(sub("^[^=]+=", "", names(fit$strata)), fit$strata)
  tab <- summary(fit)$table
  if (is.null(dim(tab))) tab <- t(as.matrix(tab))
  chk <- summary(fit, times = KM_YEARS, extend = TRUE)
  chk_grp <- if (is.null(chk$strata)) rep(groups, length(chk$time)) else sub("^[^=]+=", "", as.character(chk$strata))
  lapply(seq_along(groups), function(i) {
    g <- groups[i]
    d <- if (is.null(var)) data else data[data[[var]] == g, ]
    st <- if ("start" %in% names(d)) d$start else rep(0, nrow(d))
    risk_at  <- function(u) sum(st < u & d$stop >= u)          # people at risk at step u
    min_risk <- function(t) min(vapply(seq_len(t), risk_at, 0))  # weakest step up to t
    sel <- grp == g
    curve <- data.frame(time = c(0, fit$time[sel]), surv = c(1, fit$surv[sel]),
                        lower = c(1, fit$lower[sel]), upper = c(1, fit$upper[sel]),
                        n_risk = c(risk_at(1), fit$n.risk[sel]), n_event = c(0, fit$n.event[sel]))
    cs <- chk_grp == g
    retention <- data.frame(year = chk$time[cs], surv = chk$surv[cs],
                            lower = chk$lower[cs], upper = chk$upper[cs])
    retention$min_n_risk <- vapply(retention$year, min_risk, 0)
    retention$reliable   <- retention$min_n_risk >= KM_MIN_RISK
    retention$surv[retention$min_n_risk == 0] <- NA            # nobody observed: not estimable
    med <- unname(tab[i, "median"])
    supported <- which(vapply(1:20, risk_at, 0) >= KM_MIN_RISK)
    list(group = g, n = nrow(d), events = sum(d$event),
         median_years = med,
         median_ci = unname(tab[i, c("0.95LCL", "0.95UCL")]),
         median_reliable = !is.na(med) && min_risk(med) >= KM_MIN_RISK,
         display_max_time = if (length(supported)) max(supported) else 0,
         sparse_steps = if (length(supported)) setdiff(seq_len(max(supported)), supported) else integer(0),
         retention = retention, curve = curve)
  })
}

km <- list(
  overall      = km_groups(km_all, surv_df)[[1]],
  by_overtime  = list(logrank = score_test("OverTime"), groups = km_groups(km_ot, surv_df, "OverTime")),
  by_job_level = list(logrank = score_test("JobLevel"), groups = km_groups(km_jl, surv_df, "JobLevel")))

# The same question without the survival machinery: exit rate in each tenure year.
exit_rates <- function(d) {
  d %>% mutate(tenure_year = pmin(YearsAtCompany + 1, 11)) %>%
    group_by(tenure_year) %>%
    summarise(at_risk = n(), leavers = sum(left), .groups = "drop") %>%
    mutate(label = ifelse(tenure_year == 11, "11+", as.character(tenure_year)),
           rate = leavers / at_risk) %>%
    select(tenure_year, label, at_risk, leavers, rate)
}
exit_by_tenure <- list(overall = exit_rates(hr),
                       overtime_no  = exit_rates(filter(hr, OverTime == "No")),
                       overtime_yes = exit_rates(filter(hr, OverTime == "Yes")))

# Share of all leavers who left within their first two years (YearsAtCompany 0 or 1),
# and the first-two-years exit rate with and without overtime.
early_exit_share <- mean(hr$YearsAtCompany[hr$left == 1] <= 1)
early_rate <- hr %>% filter(YearsAtCompany <= 1) %>% group_by(OverTime) %>%
  summarise(n = n(), rate = mean(left), .groups = "drop")

## ---- survival-naive ----
# The textbook version, kept for comparison: time = tenure, stayers censored, no
# delayed entry (stop = YearsAtCompany + 1 so the steps line up with the curve above).
km_naive_all <- survfit(Surv(stop, event) ~ 1,         data = surv_df)
km_naive_ot  <- survfit(Surv(stop, event) ~ OverTime,  data = surv_df)
km_naive_jl  <- survfit(Surv(stop, event) ~ JobLevel5, data = surv_df)
naive_df <- select(surv_df, -start)
km_naive <- list(
  overall      = km_groups(km_naive_all, naive_df)[[1]],
  by_overtime  = list(logrank = logrank(survdiff(Surv(stop, event) ~ OverTime, data = surv_df)),
                      groups  = km_groups(km_naive_ot, naive_df, "OverTime")),
  by_job_level = list(logrank = logrank(survdiff(Surv(stop, event) ~ JobLevel5, data = surv_df)),
                      groups  = km_groups(km_naive_jl, naive_df, "JobLevel5")))

## ---- cox ----
# Cox proportional hazards with delayed entry, on levers HR can act on plus marital
# status as a control. Hazard ratio > 1 = leaves sooner at the same tenure.
cox_terms <- c("Overtime", "EntryLevel", "NoStockOptions", "Single", "FrequentTravel",
               "LowJobSatisfaction", "LowEnvironmentSatisfaction")
cox_df  <- model_df %>% mutate(start = hr$YearsAtCompany, stop = start + 1, event = left)
cox_rhs <- paste(cox_terms, collapse = " + ")
cox_fit <- coxph(as.formula(paste("Surv(start, stop, event) ~", cox_rhs)), data = cox_df)
cox_zph <- cox.zph(cox_fit)                       # proportional-hazards check
cox_tab <- tidy(cox_fit, exponentiate = TRUE, conf.int = TRUE) %>%
  transmute(term, label = unname(term_labels[term]), hazard_ratio = estimate,
            ci_low = conf.low, ci_high = conf.high, p_value = p.value,
            significant = p.value < 0.05) %>%
  arrange(desc(hazard_ratio))

# Same model without delayed entry: tenure-linked traits (job level) look far
# stronger than they are, which is the left-truncation bias in action.
cox_naive <- coxph(as.formula(paste("Surv(stop, event) ~", cox_rhs)), data = cox_df)
cox_naive_tab <- tidy(cox_naive, exponentiate = TRUE, conf.int = TRUE) %>%
  transmute(term, hazard_ratio_naive = estimate)

## ---- tree ----
# A regression tree on the 0/1 outcome (method = "anova"): each leaf's mean IS its
# attrition rate, and splits maximise the difference in rates. (A "class" tree on a
# 16% outcome refuses to split the big low-risk branch because no split changes
# the majority vote, which hides useful segments.)
tree_df <- hr %>% transmute(
  left, OverTime, JobLevel, StockOptionLevel, MaritalStatus, Age, MonthlyIncome,
  YearsAtCompany, TotalWorkingYears, JobRole, BusinessTravel, Department,
  JobSatisfaction, EnvironmentSatisfaction, WorkLifeBalance, JobInvolvement,
  DistanceFromHome, NumCompaniesWorked, YearsWithCurrManager) %>%
  mutate(across(where(is.character), factor))

set.seed(SEED)
tree_ctrl <- rpart.control(cp = 0.01, minbucket = 30, maxdepth = 4, xval = 10)
tree <- rpart(left ~ ., data = tree_df, method = "anova", control = tree_ctrl)

pretty_var <- c(
  OverTime = "Overtime", JobLevel = "Job level", StockOptionLevel = "Stock option level",
  MaritalStatus = "Marital status", Age = "Age", MonthlyIncome = "Monthly income",
  YearsAtCompany = "Years at company", TotalWorkingYears = "Total working years",
  JobRole = "Job role", BusinessTravel = "Business travel", Department = "Department",
  JobSatisfaction = "Job satisfaction", EnvironmentSatisfaction = "Environment satisfaction",
  WorkLifeBalance = "Work-life balance", JobInvolvement = "Job involvement",
  DistanceFromHome = "Distance from home", NumCompaniesWorked = "Prior employers",
  YearsWithCurrManager = "Years with current manager")
rating_vars <- c("JobSatisfaction", "EnvironmentSatisfaction", "JobInvolvement")

# Turn rpart's path ("JobLevel< 1.5", "OverTime=Yes", ...) into readable conditions:
# merge repeated splits on one variable and snap integer thresholds to whole values.
readable_conditions <- function(path) {
  parts <- regmatches(path, regexec("^([A-Za-z]+)\\s*(>=|<=|<|>|=)\\s*(.*)$", path))
  acc <- list()
  for (p in parts) {
    v <- p[2]; op <- p[3]; val <- p[4]
    if (is.null(acc[[v]])) acc[[v]] <- list(lo = NULL, hi = NULL, set = NULL)
    if (op == "=") {
      lv <- strsplit(val, ",")[[1]]
      acc[[v]]$set <- if (is.null(acc[[v]]$set)) lv else intersect(acc[[v]]$set, lv)
    } else if (op %in% c(">=", ">")) {
      acc[[v]]$lo <- max(acc[[v]]$lo, as.numeric(val))
    } else {
      acc[[v]]$hi <- min(acc[[v]]$hi, as.numeric(val))
    }
  }
  vapply(names(acc), function(v) {
    a <- acc[[v]]; nm <- pretty_var[[v]]
    if (!is.null(a$set)) {
      lv <- gsub("_", " ", a$set)
      return(if (length(lv) == 1) paste(nm, "=", lv) else paste0(nm, ": ", paste(lv, collapse = " or ")))
    }
    x <- tree_df[[v]]
    lo <- if (is.null(a$lo)) NULL else ceiling(a$lo)          # x >= 1.5  ->  x >= 2
    hi <- if (is.null(a$hi)) NULL else ceiling(a$hi) - 1      # x <  1.5  ->  x <= 1
    if (!is.null(lo) && lo <= min(x)) lo <- NULL
    if (!is.null(hi) && hi >= max(x)) hi <- NULL
    lab <- function(k) {
      if (v %in% rating_vars) return(paste0(k, " (", rating_lab[k], ")"))
      if (v == "WorkLifeBalance") return(paste0(k, " (", wlb_lab[k], ")"))
      num(k)
    }
    if (!is.null(lo) && !is.null(hi)) {
      if (lo == hi) paste(nm, "=", lab(lo)) else paste0(nm, " ", num(lo), dash, num(hi))
    } else if (!is.null(lo)) {
      if (lo == max(x)) paste(nm, "=", lab(lo)) else paste(nm, "\u2265", num(lo))
    } else if (!is.null(hi)) {
      if (hi == min(x)) {
        paste(nm, "=", lab(hi))
      } else if (length(unique(x)) > 50) {
        paste(nm, "<", num(ceiling(a$hi)))                  # wide numeric: keep the cut point
      } else {
        paste(nm, "\u2264", num(hi))
      }
    } else {
      paste(nm, "(any)")
    }
  }, "")
}

fr <- tree$frame
leaf_nodes <- as.integer(rownames(fr)[fr$var == "<leaf>"])
paths <- path.rpart(tree, nodes = leaf_nodes, print.it = FALSE)
tree_leaves <- bind_rows(lapply(seq_along(leaf_nodes), function(i) {
  row <- fr[rownames(fr) == as.character(leaf_nodes[i]), ]
  conds <- readable_conditions(paths[[i]][-1])                # drop "root"
  data.frame(node = leaf_nodes[i], rule = paste(conds, collapse = " & "),
             n = row$n, leavers = round(row$n * row$yval), rate = row$yval,
             stringsAsFactors = FALSE) %>%
    mutate(conditions = list(I(unname(conds))))              # I(): stays a JSON array even with one condition
})) %>%
  mutate(share_of_employees = n / n_emp, share_of_leavers = leavers / n_left,
         lift = rate / overall_rate,
         rule_text = sprintf("%s \u2192 %s leave (n = %s)", rule, pct(rate), num(n))) %>%
  arrange(desc(rate))

tree_importance <- data.frame(variable = names(tree$variable.importance),
                              importance = unname(tree$variable.importance)) %>%
  mutate(label = unname(pretty_var[variable]), importance = 100 * importance / sum(importance))
tree_cp <- as.data.frame(tree$cptable)

## ---- whatif ----
# Using the full-data logistic model: each overtime worker's predicted probability
# of leaving now, and the same person's probability with Overtime switched to 0.
# Associational, not causal: "if they had the attrition odds of comparable
# colleagues who do not work overtime".
p_all   <- fitted(fit_full)
is_ot   <- model_df$Overtime == 1
cf      <- model_df[is_ot, ]
cf$Overtime <- 0
p_no_ot <- unname(predict(fit_full, newdata = cf, type = "response"))
delta   <- p_all[is_ot] - p_no_ot

base_expected <- sum(p_all)     # equals the observed leavers: a property of logistic MLE
n_ot <- sum(is_ot)
delta_sorted <- sort(delta, decreasing = TRUE)
scenarios <- data.frame(share = OT_SHARES) %>%
  mutate(workers_moved = round(share * n_ot),
         # random: a share s of overtime workers, chosen at random -> linear in s
         expected_leavers_random   = base_expected - share * sum(delta),
         # targeted: the workers with the largest predicted drop go first
         expected_leavers_targeted = base_expected - vapply(workers_moved, function(k) sum(delta_sorted[seq_len(k)]), 0),
         reduction_random   = base_expected - expected_leavers_random,
         reduction_targeted = base_expected - expected_leavers_targeted,
         attrition_rate_random   = expected_leavers_random / n_emp,
         attrition_rate_targeted = expected_leavers_targeted / n_emp)

# Naive comparison for context: overtime workers at the raw non-overtime rate.
rate_ot    <- mean(hr$left[hr$OverTime == "Yes"])
rate_no_ot <- mean(hr$left[hr$OverTime == "No"])
naive_reduction <- n_ot * (rate_ot - rate_no_ot)

ot_emp <- hr[is_ot, ] %>%
  transmute(emp_no = EmployeeNumber, p_now = unname(p_all[is_ot]), p_no_ot = p_no_ot,
            monthly_income = MonthlyIncome, job_level = JobLevel, department = Department,
            left = left) %>%
  arrange(desc(p_now - p_no_ot))

# Inputs for a user-chosen replacement-cost assumption (no cost figure is asserted here).
cost_inputs <- list(
  avg_monthly_income_leavers    = mean(hr$MonthlyIncome[hr$left == 1]),
  median_monthly_income_leavers = median(hr$MonthlyIncome[hr$left == 1]),
  avg_monthly_income_all        = mean(hr$MonthlyIncome),
  avg_monthly_income_ot_leavers = mean(hr$MonthlyIncome[hr$left == 1 & hr$OverTime == "Yes"]),
  # income of the leavers the full what-if would avoid, weighted by each person's drop in risk
  avg_monthly_income_avoided    = sum(delta * hr$MonthlyIncome[is_ot]) / sum(delta))

## ---- insights ----
lvl <- function(key, level) {
  l <- segments[[key]]$levels
  l[l$level == level, ]
}
or_of  <- function(term) or_tab[or_tab$term == term, ]
ci_txt <- function(lo, hi) sprintf("95%% CI %.1f%s%.1f", lo, dash, hi)

ot_or   <- or_of("Overtime")
lvl1    <- lvl("JobLevel", "Level 1")
lvl2p   <- hr %>% filter(JobLevel >= 2) %>% summarise(r = mean(left)) %>% pull(r)
stock0  <- lvl("StockOptionLevel", "Level 0")
stock1p <- hr %>% filter(StockOptionLevel >= 1) %>% summarise(r = mean(left)) %>% pull(r)
single  <- lvl("MaritalStatus", "Single")
travel  <- lvl("BusinessTravel", "Travels frequently")
young   <- lvl("AgeBand", paste0("18", dash, "24"))
ret_at  <- function(g, y) g$retention$surv[g$retention$year == y]
ret1    <- ret_at(km$overall, 1)
ret2    <- ret_at(km$overall, 2)
ret10   <- ret_at(km$overall, 10)
t01     <- lvl("TenureBand", paste0("0", dash, "1 yrs"))
t59     <- lvl("TenureBand", paste0("5", dash, "9 yrs"))
t10p    <- lvl("TenureBand", "10+ yrs")
ot_hr   <- cox_tab[cox_tab$term == "Overtime", ]
early_ot <- early_rate$rate[early_rate$OverTime == "Yes"]
early_no <- early_rate$rate[early_rate$OverTime == "No"]
top_leaf <- tree_leaves %>% filter(n >= 30) %>% slice(1)
low_leaf <- tree_leaves %>% arrange(rate) %>% slice(1)
all_ot  <- scenarios[scenarios$share == 1, ]
half_ot <- scenarios[scenarios$share == 0.5, ]
adj_phrase <- if (all_ot$reduction_random < 0.9 * naive_reduction) {
  "adjusting for who works overtime shrinks the estimate"
} else if (all_ot$reduction_random > 1.1 * naive_reduction) {
  "adjusting for who works overtime makes the effect larger, not smaller"
} else {
  "close to the model, so the overtime effect is not explained away by who works overtime"
}

insights <- list(
  list(id = "overall", source = "baseline",
       title = "About 1 in 6 employees left",
       text = sprintf("%s of employees (%s of %s) left the company.", pct(overall_rate, 1), num(n_left), num(n_emp)),
       value = overall_rate, value_label = "attrition rate"),
  list(id = "overtime", source = "baseline + logistic",
       title = "Overtime is the sharpest single divider",
       text = sprintf("%s of overtime workers left vs %s of everyone else (%.1f\u00d7). Holding the other factors constant, overtime multiplies the odds of leaving by %.1f (%s).",
                      pct(rate_ot), pct(rate_no_ot), rate_ot / rate_no_ot, ot_or$odds_ratio, ci_txt(ot_or$ci_low, ot_or$ci_high)),
       value = ot_or$odds_ratio, value_label = "odds ratio, overtime"),
  list(id = "early_tenure", source = "baseline + survival",
       title = "Exits cluster in the first two years",
       text = sprintf("%s of employees in their first two years left, vs %s at 5%s9 years and %s at 10+. At these rates a new hire has a %s chance of completing year 1 and %s of completing year 2 (Kaplan-Meier, delayed entry).",
                      pct(t01$rate), pct(t59$rate), dash, pct(t10p$rate), pct(ret1), pct(ret2)),
       value = t01$rate, value_label = "exit rate, first two years"),
  list(id = "overtime_survival", source = "survival (Cox)",
       title = "Overtime workers leave sooner at every tenure",
       text = sprintf("At the same tenure, overtime workers leave at %.1f%s the rate of others (Cox hazard ratio, %s; log-rank p %s). In their first two years, %s of overtime workers left vs %s of the rest.",
                      ot_hr$hazard_ratio, "\u00d7", ci_txt(ot_hr$ci_low, ot_hr$ci_high),
                      fmt_p(km$by_overtime$logrank$p_value), pct(early_ot), pct(early_no)),
       value = ot_hr$hazard_ratio, value_label = "hazard ratio, overtime"),
  list(id = "junior_equity", source = "baseline",
       title = "Junior staff without equity are the most exposed",
       text = sprintf("Job level 1: %s leave vs %s at level 2+. No stock options: %s vs %s with any.",
                      pct(lvl1$rate), pct(lvl2p), pct(stock0$rate), pct(stock1p)),
       value = lvl1$rate, value_label = "attrition rate, job level 1"),
  list(id = "top_segment", source = "decision tree",
       title = "The riskiest segment the tree finds",
       text = sprintf("%s: %s leave (%s people, %s the company average). Lowest-risk segment: %s at %s.",
                      top_leaf$rule, pct(top_leaf$rate), num(top_leaf$n),
                      sprintf("%.1f\u00d7", top_leaf$lift), low_leaf$rule, pct(low_leaf$rate)),
       value = top_leaf$rate, value_label = "attrition rate, top tree segment"),
  list(id = "profile", source = "baseline",
       title = "Other strong signals",
       text = sprintf("Single employees: %s. Frequent travellers: %s. Ages 18%s24: %s. Company average: %s.",
                      pct(single$rate), pct(travel$rate), dash, pct(young$rate), pct(overall_rate)),
       value = single$rate, value_label = "attrition rate, single employees"),
  list(id = "model", source = "logistic validation",
       title = "Risk can be ranked, imperfectly",
       text = sprintf("On %s held-out employees the model scores AUC %.2f (overtime alone: %.2f). Flagging the riskiest 20%% catches %s of leavers, and %s of those flagged actually left (vs %s base rate).",
                      num(nrow(test)), auc_test, auc_ot_only, pct(cm$recall), pct(cm$precision), pct(cm$base_rate)),
       value = auc_test, value_label = "test AUC"),
  list(id = "whatif", source = "what-if (logistic)",
       title = "What overtime might be worth",
       text = sprintf("If no one worked overtime, the model expects %s leavers instead of %s (%s fewer, about %s of overtime workers' exits). Taking half of overtime workers off overtime, highest-impact first: %s fewer. The raw rate gap gives %s fewer, %s.",
                      num(all_ot$expected_leavers_random), num(base_expected), num(all_ot$reduction_random),
                      pct(all_ot$reduction_random / sum(hr$left[is_ot])), num(half_ot$reduction_targeted),
                      num(naive_reduction), adj_phrase),
       value = all_ot$reduction_random, value_label = "expected leavers avoided, all overtime removed")
)

recommendations <- list(
  list(id = "overtime_policy",
       title = "Pilot an overtime cap where overtime is chronic",
       hypothesis = "Cutting sustained overtime lowers voluntary attrition among the people who work it.",
       action = "Cap or rotate overtime in a few comparable teams for two quarters; leave matched teams as they are.",
       measure = "12-month voluntary attrition and engagement of overtime workers, pilot vs matched teams.",
       evidence = sprintf("Overtime odds ratio %.1f; model-based ceiling of about %s fewer leavers out of %s in this sample.",
                          ot_or$odds_ratio, num(all_ot$reduction_random), num(n_left))),
  list(id = "early_tenure",
       title = "Strengthen the first two years",
       hypothesis = "Structured onboarding and early check-ins reduce first- and second-year exits.",
       action = "Add 90-day and 12-month stay conversations, a buddy, and a clear first-promotion path for new hires.",
       measure = "Kaplan-Meier retention at 12 and 24 months for new-hire cohorts before vs after the change.",
       evidence = sprintf("%s of first- and second-year employees left (company average %s); at these rates only %s of new hires complete year 2.",
                          pct(t01$rate), pct(overall_rate), pct(ret2))),
  list(id = "junior_equity",
       title = "Test a retention stake for junior staff",
       hypothesis = "Stock options or a deferred retention bonus at job level 1 increase tenure.",
       action = "Extend a small equity or deferred-bonus grant to level-1 staff without options, phased in by site so the late sites act as a comparison.",
       measure = "Attrition of eligible vs not-yet-eligible level-1 staff at 12 and 24 months, against the grant cost.",
       evidence = sprintf("Job level 1: %s attrition; no stock options: %s. (In this sample every single employee has no options, so the two signals overlap.)",
                          pct(lvl1$rate), pct(stock0$rate))),
  list(id = "risk_conversations",
       title = "Use risk scores to start conversations, not to decide",
       hypothesis = "Stay interviews with the highest-risk group prevent some exits.",
       action = "Give managers the top-20% list for stay interviews, plus a random comparison group; never use the score for pay, promotion or exit decisions, and keep protected traits out of targeting.",
       measure = "Exits among interviewed vs comparison employees; how many flagged people actually leave.",
       evidence = sprintf("Top 20%% by risk holds %s of leavers at %s precision (base rate %s).",
                          pct(cm$recall), pct(cm$precision), pct(cm$base_rate)))
)

caveats <- c(
  "The data is a fictional sample created by IBM data scientists, not records of a real company. Patterns are illustrative.",
  "It is one cross-sectional snapshot, so every result is an association. Nothing here proves that changing a factor changes attrition; the recommendations are hypotheses to test.",
  "IBM does not document the attrition window. The survival curves assume one year and use delayed entry, so they describe a synthetic cohort at this year's exit rates. Tenure is in whole years, and overtime and job level are measured today, not over each career.",
  sprintf("The hold-out set has %s people and %s leavers, so AUC, precision and recall carry real sampling noise.", num(nrow(test)), num(sum(test$left))),
  "In this sample every single employee has stock-option level 0, so the marital-status and stock-option effects are entangled; read them together.",
  "Age and marital status are included only as statistical controls. Decisions about individuals should not use protected characteristics."
)

## ---- export ----
r4  <- function(x) round(x, 4)
s3  <- function(x) signif(x, 3)
rnd <- function(df, cols, f = r4) { for (cc in intersect(cols, names(df))) df[[cc]] <- f(df[[cc]]); df }
prob_cols <- c("rate", "ci_low", "ci_high", "lift", "surv", "lower", "upper", "mean_predicted",
               "actual_rate", "p_min", "p_max", "share_of_leavers", "precision", "share_flagged",
               "fpr", "tpr", "share_of_employees", "importance", "attrition_rate_random",
               "attrition_rate_targeted", "p_now", "p_no_ot", "time", "median_years")

seg_out <- lapply(unname(segments), function(s) list(
  key = s$key, label = s$label, kind = s$kind, chi2 = round(s$chi2, 2), df = s$df,
  p_value = s3(s$p_value), cramers_v = r4(s$cramers_v), significant = s$significant,
  min_expected = round(s$min_expected, 1),
  levels = rnd(s$levels, prob_cols)))

km_out <- function(g, with_curve = TRUE) {
  o <- list(group = g$group, n = g$n, events = g$events,
            median_years = if (is.na(g$median_years)) NULL else g$median_years,
            median_ci = I(g$median_ci), median_reliable = g$median_reliable,       # I() = always an array
            display_max_time = g$display_max_time, sparse_steps = I(g$sparse_steps),
            retention = rnd(g$retention, prob_cols))
  if (with_curve) o$curve <- rnd(g$curve, prob_cols)
  o
}
test_out <- function(t) list(method = t$method, chi2 = round(t$chi2, 2), df = t$df, p_value = s3(t$p_value))

out <- list(
  meta = list(
    title = "Who leaves, and why? People analytics in R",
    author = "Rita Moreira",
    generated_by = "analysis/people_attrition.R",
    generated_on = format(Sys.Date()),
    r_version = paste(R.version$major, R.version$minor, sep = "."),
    source = list(name = "IBM HR Analytics Employee Attrition & Performance (sample)",
                  url = "https://github.com/IBM/employee-attrition-aif360/blob/master/data/emp_attrition.csv",
                  fictional = TRUE,
                  note = "Fictional data created by IBM data scientists; not records of a real company."),
    rows = n_emp, columns_kept = length(expected_cols) - length(const_cols),
    dropped_constant_columns = const_cols, seed = SEED, report = "reports/people_attrition.html"),
  overview = list(employees = n_emp, leavers = n_left, attrition_rate = r4(overall_rate),
                  stayers = n_emp - n_left, overtime_workers = n_ot,
                  overtime_rate = r4(rate_ot), no_overtime_rate = r4(rate_no_ot),
                  early_exit_share = r4(early_exit_share)),
  segments = list(
    note = "Variables ordered by Cramer's V (strongest association first). Ordinal levels in natural order; nominal levels by rate, highest first. Chi-square is Pearson without continuity correction.",
    variables = seg_out,
    top_levels = rnd(top_levels, prob_cols)),
  logit = list(
    formula = paste("left ~", paste(predictors, collapse = " + ")),
    fit_on = "all employees (odds ratios); training split (validation)",
    n = nrow(model_df), events = sum(model_df$left),
    aic = round(AIC(fit_full), 1), pseudo_r2_mcfadden = r4(pseudo_r2),
    odds_ratios = or_tab %>% mutate(across(c(odds_ratio, ci_low, ci_high), ~ round(.x, 3)), p_value = s3(p_value)),
    validation = list(
      split = "70/30 stratified on Attrition, set.seed(2026)",
      train_n = nrow(train), train_events = sum(train$left),
      test_n = nrow(test), test_events = sum(test$left),
      auc_test = r4(auc_test), auc_train = r4(auc_train), auc_overtime_only = r4(auc_ot_only),
      brier_test = r4(brier),
      calibration = rnd(calib, prob_cols),
      top20 = lapply(cm, function(v) if (is.double(v)) r4(v) else v),
      gains = rnd(gains %>% select(-k), prob_cols),
      roc = rnd(roc, prob_cols))),
  survival = list(
    method = "Kaplan-Meier with delayed entry (left truncation): Surv(start = YearsAtCompany, stop = YearsAtCompany + 1, event = Attrition == 'Yes'); stayers censored at stop.",
    assumption = "Attrition covers a one-year observation window (IBM does not document it). Employees who left in earlier years are absent from the file, so each person is at risk only during the tenure year they were observed in.",
    time_definition = "time = years since joining (integer steps). surv at t = share of a synthetic new-hire cohort still employed after t years if this year's exit rates by tenure held.",
    min_risk_for_display = KM_MIN_RISK,
    overall = km_out(km$overall),
    by_overtime = list(logrank = test_out(km$by_overtime$logrank),
                       groups = lapply(km$by_overtime$groups, km_out)),
    by_job_level = list(note = "Job levels 3, 4 and 5 are pooled: levels 4 and 5 have 0-6 people in each early tenure year.",
                        logrank = test_out(km$by_job_level$logrank),
                        groups = lapply(km$by_job_level$groups, km_out)),
    exit_rate_by_tenure = lapply(exit_by_tenure, function(d) rnd(d, prob_cols)),
    cox = list(
      method = "coxph with delayed entry (same start/stop as the curves)",
      formula = paste("Surv(start, stop, event) ~", cox_rhs),
      n = cox_fit$n, events = cox_fit$nevent,
      concordance = r4(unname(cox_fit$concordance["concordance"])),
      ph_test_global_p = s3(cox_zph$table["GLOBAL", "p"]),
      hazard_ratios = cox_tab %>% mutate(across(c(hazard_ratio, ci_low, ci_high), ~ round(.x, 3)), p_value = s3(p_value))),
    naive = list(
      method = "Textbook Kaplan-Meier: time = YearsAtCompany (+1 so steps align), stayers censored, no delayed entry; survdiff log-rank. Kept for comparison only.",
      why_not_primary = sprintf("It keeps long-tenured stayers in the early risk sets although their early years were never observed, so it understates early exits: it puts year-1 retention at %s while %s of first-year employees in the file left.",
                                pct(ret_at(km_naive$overall, 1), 1), pct(exit_by_tenure$overall$rate[1])),
      overall = km_out(km_naive$overall),
      by_overtime = list(logrank = test_out(km_naive$by_overtime$logrank),
                         groups = lapply(km_naive$by_overtime$groups, km_out, with_curve = FALSE)),
      by_job_level = list(logrank = test_out(km_naive$by_job_level$logrank),
                          groups = lapply(km_naive$by_job_level$groups, km_out, with_curve = FALSE)),
      cox_hazard_ratios = cox_naive_tab %>% mutate(hazard_ratio_naive = round(hazard_ratio_naive, 3)))),
  tree = list(
    method = "rpart, method = 'anova' on the 0/1 outcome (leaf mean = attrition rate), fit on all employees",
    control = list(cp = tree_ctrl$cp, minbucket = tree_ctrl$minbucket, maxdepth = tree_ctrl$maxdepth),
    n_leaves = nrow(tree_leaves),
    leaves = rnd(tree_leaves %>% select(node, rule, rule_text, conditions, n, leavers, rate,
                                        lift, share_of_employees, share_of_leavers), prob_cols),
    variable_importance = rnd(tree_importance, prob_cols),
    cp_table = data.frame(cp = s3(tree_cp$CP), nsplit = tree_cp$nsplit,
                          rel_error = r4(tree_cp$`rel error`), xerror = r4(tree_cp$xerror))),
  whatif = list(
    model = "full-data logistic regression; counterfactual sets Overtime = 0, everything else unchanged",
    observed_leavers = n_left,
    base_expected_leavers = r4(base_expected),
    overtime_workers = n_ot,
    overtime_leavers = sum(hr$left[is_ot]),
    total_risk_reduction_all_ot = r4(sum(delta)),
    naive_reduction_rate_gap = r4(naive_reduction),
    scenarios = rnd(scenarios, c(prob_cols, "expected_leavers_random", "expected_leavers_targeted",
                                 "reduction_random", "reduction_targeted")),
    employees = list(
      note = "Overtime workers only, columnar arrays, sorted by p_now - p_no_ot (largest first).",
      emp_no = ot_emp$emp_no, p_now = r4(ot_emp$p_now), p_no_ot = r4(ot_emp$p_no_ot),
      monthly_income = ot_emp$monthly_income, job_level = ot_emp$job_level,
      department = ot_emp$department, left = ot_emp$left),
    cost_inputs = c(lapply(cost_inputs, function(v) round(v, 2)),
                    list(note = "Monthly income in the dataset's own units. No replacement-cost figure is asserted: the UI applies a user-chosen multiple of annual pay (12 x monthly)."))),
  insights = lapply(insights, function(i) { i$value <- r4(i$value); i }),
  recommendations = recommendations,
  caveats = caveats
)

# jsonlite writes UTF-8; escape anything non-ASCII as \uXXXX so the file is safe
# regardless of how the page declares its charset.
ascii_json <- function(s) {
  cp <- utf8ToInt(enc2utf8(s))
  if (all(cp < 128)) return(s)
  stopifnot(all(cp <= 0xFFFF))
  ch <- character(length(cp))
  ch[cp < 128]  <- intToUtf8(cp[cp < 128], multiple = TRUE)
  ch[cp >= 128] <- sprintf("\\u%04x", cp[cp >= 128])
  paste(ch, collapse = "")
}

json <- ascii_json(as.character(toJSON(out, auto_unbox = TRUE, digits = NA, na = "null",
                                       null = "null", dataframe = "rows")))
js <- paste0("/* generated by analysis/people_attrition.R -- do not edit by hand */\n",
             "window.DATA_ATTRITION = ", json, ";\n")
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)
out_path <- file.path(OUT_DIR, "attrition.js")
con <- file(out_path, open = "wb"); writeBin(charToRaw(js), con); close(con)

cat(sprintf("Wrote %s (%.1f KB)\n", out_path, file.size(out_path) / 1024))
cat(sprintf("Attrition %.1f%% | test AUC %.3f | top-20%% recall %.1f%% precision %.1f%% | tree leaves %d\n",
            100 * overall_rate, auc_test, 100 * cm$recall, 100 * cm$precision, nrow(tree_leaves)))
