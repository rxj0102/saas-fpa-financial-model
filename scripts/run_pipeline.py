#!/usr/bin/env python3
"""End-to-end pipeline: generate data, build the three-statement model,
compute KPIs, build the Year 3 budget, simulate actuals and run variance
analysis, build the rolling cash flow forecast, and export the Excel
workbook. Prints a summary report of real output numbers.

Usage: python scripts/run_pipeline.py [--output PATH]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from saas_fpa.assumptions import OperatingAssumptions
from saas_fpa.budget_builder import budget_driver_summary, build_year3_budget, summarize_budget
from saas_fpa.cash_flow_forecast import build_rolling_forecast, scenario_summary
from saas_fpa.excel_report import build_workbook
from saas_fpa.saas_kpis import compute_kpis, kpi_snapshot
from saas_fpa.three_statement_model import validate_tie_out
from saas_fpa.variance_analysis import build_variance_table, simulate_year3_actuals, variance_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/saas_fpa_model.xlsx")
    args = parser.parse_args()

    a = OperatingAssumptions()

    print("=" * 70)
    print("1. GENERATING OPERATING DATA + THREE-STATEMENT MODEL")
    print("=" * 70)
    history, budget, state24 = build_year3_budget(a)
    actual_y3, snapshots = simulate_year3_actuals(a, state24, capture_at={36})
    combined_actual = pd.concat([history, actual_y3], ignore_index=True)

    tie_out = validate_tie_out(combined_actual)
    print(f"Tie-out check (combined 36-month actual path): {json.dumps(tie_out, indent=2)}")
    tie_out_budget = validate_tie_out(pd.concat([history, budget], ignore_index=True))
    print(f"Tie-out check (history + Year 3 budget path): {json.dumps(tie_out_budget, indent=2)}")

    print()
    print("=" * 70)
    print("2. COMPANY SCOPE")
    print("=" * 70)
    m1 = combined_actual.iloc[0]
    m36 = combined_actual.iloc[-1]
    print(f"Month 1  -> MRR ${m1['mrr_ending']:,.0f} | ARR ${m1['arr_ending']:,.0f} | "
          f"{int(m1['customers_ending'])} customers | {int(m1['headcount_total'])} employees | cash ${m1['cash']:,.0f}")
    print(f"Month 36 -> MRR ${m36['mrr_ending']:,.0f} | ARR ${m36['arr_ending']:,.0f} | "
          f"{int(m36['customers_ending'])} customers | {int(m36['headcount_total'])} employees | cash ${m36['cash']:,.0f}")
    print(f"ARR growth multiple: {m36['arr_ending'] / m1['arr_ending']:.2f}x")

    print()
    print("=" * 70)
    print("3. SAAS KPIS")
    print("=" * 70)
    kpis = compute_kpis(combined_actual)
    snap_start = kpi_snapshot(kpis, 12)
    snap_end = kpi_snapshot(kpis, 36)
    print(f"Month 12 KPIs: {json.dumps(snap_start, indent=2, default=float)}")
    print(f"Month 36 KPIs: {json.dumps(snap_end, indent=2, default=float)}")

    print()
    print("=" * 70)
    print("4. YEAR 3 BUDGET BUILD")
    print("=" * 70)
    drivers = budget_driver_summary(a)
    budget_totals = summarize_budget(budget)
    print(f"Budget drivers: {json.dumps(drivers, indent=2, default=str)}")
    print(f"Budget totals: {json.dumps(budget_totals, indent=2, default=float)}")

    print()
    print("=" * 70)
    print("5. VARIANCE ANALYSIS (YEAR 3 ACTUAL VS. BUDGET)")
    print("=" * 70)
    vt = build_variance_table(budget, actual_y3, a)
    vsum = variance_summary(vt)
    print(f"Variance summary: {json.dumps(vsum, indent=2, default=float)}")
    material = vt[vt["material"]].sort_values("variance", key=lambda s: s.abs(), ascending=False)
    print(f"\nTop material variance line items:\n{material[['month','line_item','budget','actual','variance','variance_pct','driver_category','note']].to_string(index=False)}")

    print()
    print("=" * 70)
    print("6. ROLLING CASH FLOW FORECAST (BASE / UPSIDE / DOWNSIDE)")
    print("=" * 70)
    rolling = build_rolling_forecast(a, {24: state24, 36: snapshots[36]}, n_months=12)
    for as_of_month, fdf in rolling.items():
        starting_cash = float(fdf["cash"].iloc[0])
        summary_df = scenario_summary(fdf, starting_cash=starting_cash)
        print(f"\nForecast as of month {as_of_month}:")
        print(summary_df.to_string(index=False))

    print()
    print("=" * 70)
    print("7. EXCEL WORKBOOK")
    print("=" * 70)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    workbook_result = build_workbook(a, kpis, budget, vt, rolling, args.output)
    print(json.dumps(workbook_result, indent=2))

    print()
    print("=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
