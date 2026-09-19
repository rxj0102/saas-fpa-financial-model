"""Rolling 12-month cash flow forecast with base/upside/downside scenarios.

A forecast is branched from a snapshot of the model's state at a given
month (usually the most recent month of actuals) and run forward using the
same simulation engine as the rest of the model — so a forecast is a real
continuation of the three-statement model, not a separate spreadsheet
extrapolation. "Rolling" means the forecast is regenerated from a new
as-of point as new actuals come in; ``build_rolling_forecast`` demonstrates
this by producing forecast vintages from two different as-of points and
showing how the projection narrows/shifts as more real data arrives.

Scenarios flex two levers — new-bookings growth and logo churn — using the
multipliers in :class:`~saas_fpa.assumptions.OperatingAssumptions`:
* **base**: assumptions as planned
* **upside**: growth x``upside_growth_multiplier``, churn x``upside_churn_multiplier``
* **downside**: growth x``downside_growth_multiplier``, churn x``downside_churn_multiplier``
"""
from __future__ import annotations

import copy
from dataclasses import replace

import pandas as pd

from .assumptions import OperatingAssumptions
from .data_generator import SimState, run_months

SCENARIOS = ("downside", "base", "upside")


def _scenario_assumptions(a: OperatingAssumptions, scenario: str) -> OperatingAssumptions:
    if scenario == "base":
        return a
    if scenario == "upside":
        g_mult, c_mult = a.upside_growth_multiplier, a.upside_churn_multiplier
    elif scenario == "downside":
        g_mult, c_mult = a.downside_growth_multiplier, a.downside_churn_multiplier
    else:
        raise ValueError(f"unknown scenario: {scenario}")
    return replace(
        a,
        new_bookings_growth_rate_start=a.new_bookings_growth_rate_start * g_mult,
        new_bookings_growth_rate_end=a.new_bookings_growth_rate_end * g_mult,
        logo_churn_rate_start=a.logo_churn_rate_start * c_mult,
        logo_churn_rate_end=a.logo_churn_rate_end * c_mult,
    )


def forecast_scenario(
    a: OperatingAssumptions, state_as_of: SimState, as_of_month: int, scenario: str, n_months: int = 12
) -> pd.DataFrame:
    """Project ``n_months`` forward from ``state_as_of`` under one scenario."""
    scenario_a = _scenario_assumptions(a, scenario)
    state = copy.deepcopy(state_as_of)
    forecast_months = range(as_of_month + 1, as_of_month + 1 + n_months)
    df, _, _ = run_months(scenario_a, forecast_months, state)
    df = df.copy()
    df["scenario"] = scenario
    df["as_of_month"] = as_of_month
    return df


def forecast_all_scenarios(
    a: OperatingAssumptions, state_as_of: SimState, as_of_month: int, n_months: int = 12
) -> pd.DataFrame:
    """Run all three scenarios from the same as-of point and stack them."""
    frames = [forecast_scenario(a, state_as_of, as_of_month, s, n_months) for s in SCENARIOS]
    return pd.concat(frames, ignore_index=True)


def scenario_summary(forecast_df: pd.DataFrame, starting_cash: float) -> pd.DataFrame:
    """One row per scenario: ending cash, min cash, and implied runway."""
    rows = []
    for scenario in SCENARIOS:
        sub = forecast_df[forecast_df["scenario"] == scenario].sort_values("month")
        ending_cash = float(sub["cash"].iloc[-1])
        min_cash = float(sub["cash"].min())
        avg_net_burn = float((-sub["cfo"]).clip(lower=0).mean())
        runway_from_start = starting_cash / avg_net_burn if avg_net_burn > 0 else float("inf")
        rows.append(
            dict(
                scenario=scenario,
                ending_arr=float(sub["arr_ending"].iloc[-1]),
                ending_cash=ending_cash,
                min_cash=min_cash,
                min_cash_month=int(sub.loc[sub["cash"].idxmin(), "month"]),
                avg_net_burn=avg_net_burn,
                runway_months_from_as_of=runway_from_start,
                cash_runs_out=bool((sub["cash"] <= 0).any()),
            )
        )
    return pd.DataFrame(rows)


def build_rolling_forecast(
    a: OperatingAssumptions,
    snapshots: dict[int, SimState],
    n_months: int = 12,
) -> dict[int, pd.DataFrame]:
    """Produce a forecast vintage (all 3 scenarios) from each as-of month in
    ``snapshots``, demonstrating the "rolling" behavior: as later, more
    complete actuals become available, a new forecast supersedes the
    earlier one branched from a less-informed point in time."""
    return {
        as_of_month: forecast_all_scenarios(a, state, as_of_month, n_months)
        for as_of_month, state in sorted(snapshots.items())
    }
