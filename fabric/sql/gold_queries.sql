-- Queries for the lakehouse SQL analytics endpoint (T-SQL, read-only).
-- Open airline_lakehouse > switch to "SQL analytics endpoint" > New SQL query, paste one block, Run.

-- 1. Did reliability change after the merger closed (2024-09-18)? A14 by airline and phase.
SELECT carrier,
       merger_phase,
       SUM(flights)                                   AS flights,
       CAST(SUM(a14 * arrived) / SUM(arrived) AS DECIMAL(5, 4)) AS a14,
       CAST(SUM(cancelled) * 1.0 / SUM(flights) AS DECIMAL(5, 4)) AS cancel_rate
FROM gold_carrier_month_kpi
WHERE carrier IN ('AS', 'HA')
GROUP BY carrier, merger_phase
ORDER BY carrier, MIN(month);

-- 2. The five days that broke the combined operation.
SELECT TOP 5 [date], flights, cancelled, diverted, late15,
       CAST(disruption_share AS DECIMAL(5, 4)) AS disruption_share
FROM gold_daily_disruption
WHERE carrier = 'AS+HA'
ORDER BY worst_day_rank;

-- 3. Where the two networks compete today.
SELECT market, as_flights, ha_flights, miles
FROM gold_market_overlap
WHERE both_carriers = 1
ORDER BY as_flights + ha_flights DESC;

-- 4. How much delay is inherited from the aircraft's previous leg?
SELECT carrier, cause, minutes, CAST(share AS DECIMAL(5, 4)) AS share
FROM gold_delay_cause
ORDER BY carrier, minutes DESC;

-- 5. The pipeline's own health: data-quality checks and the reconciliation with the portfolio.
SELECT * FROM silver_dq_checks;
SELECT * FROM gold_portfolio_reconciliation;
