"""Core SaaS KPI calculations.

Definitions used (documented here because "NRR" and "GRR" in particular are
frequently computed inconsistently in practice):

* **NRR (Net Revenue Retention)** — of the MRR held by customers who were
  already customers at the start of the period, what fraction remains after
  churn, contraction, *and* expansion? New-logo bookings are excluded.
  Monthly NRR = (beginning MRR - churned MRR + expansion MRR - contraction
  MRR) / beginning MRR. We also report a trailing-twelve-month (TTM) NRR,
  which compounds the twelve monthly ratios — this is the number that
  matches how most SaaS companies report NRR externally, since a single
  month's ratio is noisy.
* **GRR (Gross Revenue Retention)** — the same base, but expansion is
  excluded, so GRR is capped at 100%: (beginning MRR - churned MRR -
  contraction MRR) / beginning MRR.
* **CAC** — fully-loaded: total S&M spend (headcount + programs) divided by
  new customers acquired, computed on a trailing-3-month basis to smooth
  monthly lumpiness in a small customer base.
* **LTV** — (ARPU x gross margin %) / monthly logo churn rate.
* **Rule of 40** — TTM YoY ARR growth rate (%) + TTM free-cash-flow margin
  (%). Only defined once 24 months of history exist (needs a YoY compare on
  a TTM base).
* **Magic Number** — (this quarter's revenue - prior quarter's revenue) x 4,
  divided by prior quarter's S&M spend. A classic (if crude) SaaS sales
  efficiency metric.
* **Burn rate / runway** — net burn = max(0, -operating cash flow), on a
  trailing-3-month average; runway = cash balance / trailing-3-month net
  burn, in months.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with all KPI columns appended."""
    k = df.copy()

    k["nrr_monthly"] = np.where(
        k["mrr_beginning"] > 0,
        (k["mrr_beginning"] - k["mrr_churned"] + k["mrr_expansion"] - k["mrr_contraction"]) / k["mrr_beginning"],
        np.nan,
    )
    k["grr_monthly"] = np.where(
        k["mrr_beginning"] > 0,
        (k["mrr_beginning"] - k["mrr_churned"] - k["mrr_contraction"]) / k["mrr_beginning"],
        np.nan,
    )
    k["nrr_ttm"] = k["nrr_monthly"].rolling(12).apply(lambda x: np.prod(x), raw=True)
    k["grr_ttm"] = k["grr_monthly"].rolling(12).apply(lambda x: np.prod(x), raw=True)

    sm_3mo = k["opex_sm"].rolling(3).sum()
    new_cust_3mo = k["customers_new"].rolling(3).sum()
    k["cac_trailing_3mo"] = np.where(new_cust_3mo > 0, sm_3mo / new_cust_3mo, np.nan)

    k["arpu_monthly"] = np.where(k["customers_ending"] > 0, k["mrr_ending"] / k["customers_ending"], np.nan)
    k["gross_margin_pct"] = np.where(k["revenue"] > 0, k["gross_profit"] / k["revenue"], np.nan)
    k["ltv"] = np.where(
        k["churn_rate"] > 0,
        (k["arpu_monthly"] * k["gross_margin_pct"]) / k["churn_rate"],
        np.nan,
    )
    k["ltv_to_cac"] = np.where(k["cac_trailing_3mo"] > 0, k["ltv"] / k["cac_trailing_3mo"], np.nan)

    k["net_burn"] = (-k["cfo"]).clip(lower=0)
    k["net_burn_trailing_3mo"] = k["net_burn"].rolling(3).mean()
    k["runway_months"] = np.where(
        k["net_burn_trailing_3mo"] > 0, k["cash"] / k["net_burn_trailing_3mo"], np.inf
    )

    k["arr_yoy_growth"] = k["arr_ending"] / k["arr_ending"].shift(12) - 1

    fcf = k["cfo"] - k["capex"]
    fcf_ttm = fcf.rolling(12).sum()
    revenue_ttm = k["revenue"].rolling(12).sum()
    k["fcf_margin_ttm"] = np.where(revenue_ttm > 0, fcf_ttm / revenue_ttm, np.nan)
    k["rule_of_40"] = k["arr_yoy_growth"] * 100 + k["fcf_margin_ttm"] * 100

    quarter = ((k["month"] - 1) // 3)
    q_revenue = k.groupby(quarter)["revenue"].transform("sum")
    q_revenue_by_q = k.assign(_q=quarter).groupby("_q")["revenue"].sum()
    q_sm_by_q = k.assign(_q=quarter).groupby("_q")["opex_sm"].sum()
    prior_q_revenue = quarter.map(lambda qi: q_revenue_by_q.get(qi - 1, np.nan))
    prior_q_sm = quarter.map(lambda qi: q_sm_by_q.get(qi - 1, np.nan))
    k["magic_number"] = np.where(
        (prior_q_sm > 0) & prior_q_revenue.notna(),
        (q_revenue - prior_q_revenue) * 4 / prior_q_sm,
        np.nan,
    )

    return k


def kpi_snapshot(k: pd.DataFrame, month: int) -> dict:
    """Return a flat dict of KPI values as of a given month, for reporting."""
    row = k.loc[k["month"] == month].iloc[0]
    return {
        "month": month,
        "mrr": row["mrr_ending"],
        "arr": row["arr_ending"],
        "customers": row["customers_ending"],
        "headcount": row["headcount_total"],
        "cash": row["cash"],
        "nrr_ttm": row.get("nrr_ttm"),
        "grr_ttm": row.get("grr_ttm"),
        "cac_trailing_3mo": row.get("cac_trailing_3mo"),
        "ltv_to_cac": row.get("ltv_to_cac"),
        "gross_margin_pct": row.get("gross_margin_pct"),
        "net_burn_trailing_3mo": row.get("net_burn_trailing_3mo"),
        "runway_months": row.get("runway_months"),
        "rule_of_40": row.get("rule_of_40"),
        "magic_number": row.get("magic_number"),
    }
