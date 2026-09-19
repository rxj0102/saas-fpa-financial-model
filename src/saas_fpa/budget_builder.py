"""Builds the Year 3 annual budget from a bottoms-up, driver-based model.

The budget is not a top-down growth-rate target dressed up as a plan — it's
produced by running the same driver-based simulation engine used for the
historical actuals (``data_generator.run_months``) forward from the actual
month-24 exit state, using the Year 3 operating plan's drivers: the
headcount hiring plan (tied to ARR milestones), the churn/expansion/
contraction schedule, the new-bookings growth curve, COGS %, and any
financing events. This mirrors how an FP&A team actually builds next year's
budget — starting from the real exit run-rate and layering the operating
plan's assumptions on top of it, not drawing a straight line through last
year's number.
"""
from __future__ import annotations

import copy

import pandas as pd

from .assumptions import OperatingAssumptions
from .data_generator import SimState, initial_state, run_months


def build_year3_budget(a: OperatingAssumptions) -> tuple[pd.DataFrame, pd.DataFrame, SimState]:
    """Simulate months 1..(budget start - 1) as history, then the budget year.

    Returns ``(history_y1_y2, year3_budget, state_at_year3_start)``. The
    returned state is a snapshot taken *before* the budget run mutates it,
    so callers (e.g. ``variance_analysis.simulate_year3_actuals``) can
    branch an independent "actual" simulation from the same true month-24
    exit point rather than continuing on top of the budget's own path.
    The two DataFrames share the same schema as ``data_generator.
    generate_history`` output, so anything downstream that expects an
    operating-data DataFrame works with either.
    """
    state = initial_state(a)
    history, state, _ = run_months(a, range(1, a.budget_year_start_month), state)
    state_at_year3_start = copy.deepcopy(state)
    budget, _, _ = run_months(a, range(a.budget_year_start_month, a.budget_year_end_month + 1), state)
    return history, budget, state_at_year3_start


def budget_driver_summary(a: OperatingAssumptions) -> dict:
    """Human-readable summary of the drivers behind the Year 3 budget, for
    reporting alongside the dollar figures."""
    y3_first, y3_last = a.budget_year_start_month, a.budget_year_end_month
    return {
        "budget_months": (y3_first, y3_last),
        "new_bookings_growth_rate_pct_range": (
            round(a.interp(a.new_bookings_growth_rate_start, a.new_bookings_growth_rate_end, y3_first) * 100, 2),
            round(a.interp(a.new_bookings_growth_rate_start, a.new_bookings_growth_rate_end, y3_last) * 100, 2),
        ),
        "logo_churn_rate_pct_range": (
            round(a.interp(a.logo_churn_rate_start, a.logo_churn_rate_end, y3_first) * 100, 2),
            round(a.interp(a.logo_churn_rate_start, a.logo_churn_rate_end, y3_last) * 100, 2),
        ),
        "expansion_rate_pct_range": (
            round(a.interp(a.monthly_expansion_rate_start, a.monthly_expansion_rate_end, y3_first) * 100, 2),
            round(a.interp(a.monthly_expansion_rate_start, a.monthly_expansion_rate_end, y3_last) * 100, 2),
        ),
        "new_customer_acv_range": (
            round(a.interp(a.starting_new_customer_acv, a.ending_new_customer_acv, y3_first), 0),
            round(a.interp(a.starting_new_customer_acv, a.ending_new_customer_acv, y3_last), 0),
        ),
        "cogs_pct_of_revenue_range": (
            round(a.interp(a.cogs_pct_of_revenue_start, a.cogs_pct_of_revenue_end, y3_first) * 100, 2),
            round(a.interp(a.cogs_pct_of_revenue_start, a.cogs_pct_of_revenue_end, y3_last) * 100, 2),
        ),
        "headcount_plan_milestones": a.headcount_plan,
        "funding_events_in_year3": [fe for fe in a.funding_events if y3_first <= fe[0] <= y3_last],
    }


def summarize_budget(budget: pd.DataFrame) -> dict:
    """Top-line Year 3 budget totals for reporting."""
    return {
        "months": (int(budget["month"].min()), int(budget["month"].max())),
        "total_revenue": float(budget["revenue"].sum()),
        "total_cogs": float(budget["cogs"].sum()),
        "total_opex": float(budget["total_opex"].sum()),
        "total_opex_sm": float(budget["opex_sm"].sum()),
        "total_opex_rd": float(budget["opex_rd"].sum()),
        "total_opex_ga": float(budget["opex_ga"].sum()),
        "ending_arr": float(budget["arr_ending"].iloc[-1]),
        "ending_customers": int(budget["customers_ending"].iloc[-1]),
        "ending_headcount": int(budget["headcount_total"].iloc[-1]),
        "ending_cash": float(budget["cash"].iloc[-1]),
    }
