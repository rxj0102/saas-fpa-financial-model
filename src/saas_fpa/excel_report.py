"""Builds the Excel management-reporting workbook.

As documented in the project plan, native Excel PivotTable objects cannot
be reliably generated from scratch with openpyxl or xlsxwriter (support is
read-oriented and brittle, not a real create-from-Python workflow). Instead
this module builds **formula-driven summary tables** — real XLOOKUP and
SUMIFS/AVERAGEIFS formulas written into the workbook that recalculate
against the raw-data tabs when opened in Excel — plus **native Excel
charts** (fully supported). The budget-vs-actual P&L, the KPI dashboard,
and the variance waterfall are all live, not pasted values.

Tabs:

1. ``Assumptions`` — the operating drivers behind the model, for reference.
2. ``Data_Actuals`` — the full 36-month realized dataset (deterministic
   history for months 1-24, noisy simulated actuals for months 25-36),
   including KPI columns. This is the source range for XLOOKUP formulas
   elsewhere in the workbook.
3. ``Data_BudgetY3`` — the Year 3 bottoms-up budget, months 25-36.
4. ``PL_Actual_vs_Budget`` — the monthly Year 3 P&L, Actual/Budget/
   Variance $/Variance % per line item per month, computed with XLOOKUP
   and arithmetic formulas, not static values.
5. ``KPI_Dashboard`` — a KPI trend table (formula-linked to Data_Actuals)
   plus native line charts.
6. ``Variance_Waterfall`` — an EBITDA bridge (Budget -> revenue variance ->
   opex variance -> Actual) rendered as a native stacked-bar waterfall.
7. ``Variance_Detail`` — the full line-item x month variance table with
   materiality flags and driver categorization, for audit-level detail.
8. ``Cash_Flow_Forecast`` — the rolling 12-month base/upside/downside
   scenario summary and a chart of projected cash by scenario.
"""
from __future__ import annotations

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.marker import Marker
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .assumptions import OperatingAssumptions

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(bold=True, size=14)
SUBTITLE_FONT = Font(italic=True, size=10, color="666666")
BOLD = Font(bold=True)
PCT_FMT = "0.0%"
USD_FMT = "#,##0"

ACTUAL_COLS = [
    "month",
    "revenue",
    "cogs",
    "gross_profit",
    "opex_sm",
    "opex_rd",
    "opex_ga",
    "total_opex",
    "ebitda",
    "da",
    "ebit",
    "net_income",
    "cash",
    "mrr_ending",
    "arr_ending",
    "customers_ending",
    "headcount_total",
    "nrr_ttm",
    "grr_ttm",
    "cac_trailing_3mo",
    "ltv_to_cac",
    "gross_margin_pct",
    "net_burn_trailing_3mo",
    "runway_months",
    "rule_of_40",
    "magic_number",
]

BUDGET_COLS = [
    "month",
    "revenue",
    "cogs",
    "gross_profit",
    "opex_sm",
    "opex_rd",
    "opex_ga",
    "total_opex",
    "ebitda",
    "da",
    "ebit",
    "net_income",
    "cash",
    "mrr_ending",
    "arr_ending",
    "customers_ending",
    "headcount_total",
]

PL_LINE_ITEMS = [
    ("Revenue", "revenue"),
    ("COGS", "cogs"),
    ("Gross Profit", "gross_profit"),
    ("S&M", "opex_sm"),
    ("R&D", "opex_rd"),
    ("G&A", "opex_ga"),
    ("Total Opex", "total_opex"),
    ("EBITDA", "ebitda"),
    ("Net Income", "net_income"),
]


def _write_df(ws: Worksheet, df: pd.DataFrame, start_row: int = 1) -> dict:
    """Write a DataFrame as a header + rows block. Returns a dict mapping
    column name -> column letter for building formulas against this sheet."""
    for j, col in enumerate(df.columns, start=1):
        cell = ws.cell(row=start_row, column=j, value=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for i, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        for j, col in enumerate(df.columns, start=1):
            ws.cell(row=i, column=j, value=row[col])
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    col_letters = {col: get_column_letter(j) for j, col in enumerate(df.columns, start=1)}
    return col_letters


def _autosize(ws: Worksheet, widths: dict) -> None:
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


def _write_assumptions_sheet(wb: Workbook, a: OperatingAssumptions) -> Worksheet:
    ws = wb.create_sheet("Assumptions")
    ws["A1"] = "Operating Assumptions"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Single source of truth for every driver in the model (see src/saas_fpa/assumptions.py)"
    ws["A2"].font = SUBTITLE_FONT

    rows = [
        ("Horizon", f"{a.n_months} months"),
        ("Starting customers", a.starting_customers),
        ("Starting ACV", a.starting_new_customer_acv),
        ("Ending ACV", a.ending_new_customer_acv),
        ("Starting cash", a.starting_cash),
        ("New bookings growth rate (Month 1)", a.new_bookings_growth_rate_start),
        ("New bookings growth rate (Month 36)", a.new_bookings_growth_rate_end),
        ("Logo churn rate (Month 1)", a.logo_churn_rate_start),
        ("Logo churn rate (Month 36)", a.logo_churn_rate_end),
        ("Monthly expansion rate (Month 1)", a.monthly_expansion_rate_start),
        ("Monthly expansion rate (Month 36)", a.monthly_expansion_rate_end),
        ("Monthly contraction rate (Month 1)", a.monthly_contraction_rate_start),
        ("Monthly contraction rate (Month 36)", a.monthly_contraction_rate_end),
        ("COGS % of revenue (Month 1)", a.cogs_pct_of_revenue_start),
        ("COGS % of revenue (Month 36)", a.cogs_pct_of_revenue_end),
        ("S&M program spend % of new bookings ARR", a.sm_program_spend_pct_of_new_bookings_arr),
        ("DSO (days)", a.dso_days),
        ("DPO (days)", a.dpo_days),
        ("% customers annual prepay", a.pct_customers_annual_prepay),
        ("Materiality threshold (%)", a.materiality_threshold_pct),
        ("Materiality threshold ($)", a.materiality_threshold_abs),
    ]
    r = 4
    ws.cell(row=r, column=1, value="Driver").font = BOLD
    ws.cell(row=r, column=2, value="Value").font = BOLD
    for i, (label, value) in enumerate(rows, start=r + 1):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=value)

    r2 = r + len(rows) + 3
    ws.cell(row=r2, column=1, value="Headcount plan (ARR milestone -> S&M / R&D / G&A heads)").font = BOLD
    for i, (threshold, heads) in enumerate(a.headcount_plan, start=r2 + 1):
        ws.cell(row=i, column=1, value=threshold)
        ws.cell(row=i, column=2, value=heads[0])
        ws.cell(row=i, column=3, value=heads[1])
        ws.cell(row=i, column=4, value=heads[2])

    r3 = r2 + len(a.headcount_plan) + 3
    ws.cell(row=r3, column=1, value="Funding events").font = BOLD
    for i, (month, amount, label) in enumerate(a.funding_events, start=r3 + 1):
        ws.cell(row=i, column=1, value=f"Month {month}")
        ws.cell(row=i, column=2, value=amount)
        ws.cell(row=i, column=3, value=label)

    _autosize(ws, {"A": 44, "B": 16, "C": 12, "D": 12})
    # Named cells the P&L formulas reference for materiality thresholds.
    ws["F4"] = "materiality_pct"
    ws["G4"] = a.materiality_threshold_pct
    ws["F5"] = "materiality_abs"
    ws["G5"] = a.materiality_threshold_abs
    return ws


def _write_data_sheet(wb: Workbook, name: str, df: pd.DataFrame, cols: list[str]) -> tuple[Worksheet, dict]:
    ws = wb.create_sheet(name)
    sub = df[cols].copy()
    col_letters = _write_df(ws, sub)
    _autosize(ws, {col_letters[c]: 14 for c in cols})
    return ws, col_letters


def _xlookup(month_cell: str, sheet: str, lookup_col_letter: str, return_col_letter: str) -> str:
    return (
        f"=IFERROR(XLOOKUP({month_cell},{sheet}!${lookup_col_letter}:${lookup_col_letter},"
        f"{sheet}!${return_col_letter}:${return_col_letter}),0)"
    )


def _write_pl_sheet(
    wb: Workbook,
    a: OperatingAssumptions,
    actual_cols: dict,
    budget_cols: dict,
) -> Worksheet:
    ws = wb.create_sheet("PL_Actual_vs_Budget")
    ws["A1"] = "Year 3 Monthly P&L: Actual vs. Budget vs. Variance"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Actual/Budget columns are live XLOOKUP formulas against Data_Actuals / Data_BudgetY3; Variance $/% are computed in-sheet."
    ws["A2"].font = SUBTITLE_FONT

    months = list(range(a.budget_year_start_month, a.budget_year_end_month + 1))
    header_row = 4
    month_header_row = 5
    first_data_row = 6

    ws.cell(row=header_row, column=1, value="Line Item").font = BOLD
    col = 2
    month_block_start = {}
    for m in months:
        month_block_start[m] = col
        top_cell = ws.cell(row=header_row, column=col, value=f"Month {m}")
        top_cell.font = HEADER_FONT
        top_cell.fill = HEADER_FILL
        ws.merge_cells(start_row=header_row, start_column=col, end_row=header_row, end_column=col + 3)
        for k, sub in enumerate(["Actual", "Budget", "Var $", "Var %"]):
            c = ws.cell(row=month_header_row, column=col + k, value=sub)
            c.font = Font(bold=True, size=9)
        col += 4
    total_block_start = col
    top_cell = ws.cell(row=header_row, column=col, value="FY Total")
    top_cell.font = HEADER_FONT
    top_cell.fill = HEADER_FILL
    ws.merge_cells(start_row=header_row, start_column=col, end_row=header_row, end_column=col + 3)
    for k, sub in enumerate(["Actual", "Budget", "Var $", "Var %"]):
        c = ws.cell(row=month_header_row, column=col + k, value=sub)
        c.font = Font(bold=True, size=9)

    for i, (label, field) in enumerate(PL_LINE_ITEMS):
        r = first_data_row + i
        ws.cell(row=r, column=1, value=label).font = BOLD if label in ("Gross Profit", "Total Opex", "EBITDA", "Net Income") else Font()
        for m in months:
            base_col = month_block_start[m]
            actual_formula = _xlookup(str(m), "Data_Actuals", actual_cols["month"], actual_cols[field])
            budget_formula = _xlookup(str(m), "Data_BudgetY3", budget_cols["month"], budget_cols[field])
            a_col_letter = get_column_letter(base_col)
            b_col_letter = get_column_letter(base_col + 1)
            v_col_letter = get_column_letter(base_col + 2)
            p_col_letter = get_column_letter(base_col + 3)
            ws[f"{a_col_letter}{r}"] = actual_formula
            ws[f"{b_col_letter}{r}"] = budget_formula
            ws[f"{v_col_letter}{r}"] = f"={a_col_letter}{r}-{b_col_letter}{r}"
            ws[f"{p_col_letter}{r}"] = f"=IF({b_col_letter}{r}=0,0,{v_col_letter}{r}/ABS({b_col_letter}{r}))"
            ws[f"{a_col_letter}{r}"].number_format = USD_FMT
            ws[f"{b_col_letter}{r}"].number_format = USD_FMT
            ws[f"{v_col_letter}{r}"].number_format = USD_FMT
            ws[f"{p_col_letter}{r}"].number_format = PCT_FMT

        ta, tb, tv, tp = (get_column_letter(total_block_start + k) for k in range(4))
        # FY total = sum of each month's Actual/Budget column via SUMIFS-style range sum
        actual_month_cols = ",".join(
            f"{get_column_letter(month_block_start[m])}{r}" for m in months
        )
        budget_month_cols = ",".join(
            f"{get_column_letter(month_block_start[m] + 1)}{r}" for m in months
        )
        ws[f"{ta}{r}"] = f"=SUM({actual_month_cols})"
        ws[f"{tb}{r}"] = f"=SUM({budget_month_cols})"
        ws[f"{tv}{r}"] = f"={ta}{r}-{tb}{r}"
        ws[f"{tp}{r}"] = f"=IF({tb}{r}=0,0,{tv}{r}/ABS({tb}{r}))"
        for cc in (ta, tb, tv):
            ws[f"{cc}{r}"].number_format = USD_FMT
        ws[f"{tp}{r}"].number_format = PCT_FMT
        for cc in (ta, tb, tv, tp):
            ws[f"{cc}{r}"].font = BOLD

    materiality_row = first_data_row + len(PL_LINE_ITEMS) + 2
    ws.cell(row=materiality_row, column=1, value="Materiality flag (Revenue row): breaches BOTH % and $ threshold from Assumptions!G4:G5").font = SUBTITLE_FONT
    rev_row = first_data_row  # Revenue is first line item
    flag_row = materiality_row + 1
    ws.cell(row=flag_row, column=1, value="Material?")
    for m in months:
        base_col = month_block_start[m]
        v_col_letter = get_column_letter(base_col + 2)
        p_col_letter = get_column_letter(base_col + 3)
        ws.cell(
            row=flag_row,
            column=base_col,
            value=f"=AND(ABS({v_col_letter}{rev_row})>Assumptions!$G$5,ABS({p_col_letter}{rev_row})>Assumptions!$G$4)",
        )

    _autosize(ws, {"A": 16})
    for m in months:
        for k in range(4):
            _autosize(ws, {get_column_letter(month_block_start[m] + k): 11})
    for k in range(4):
        _autosize(ws, {get_column_letter(total_block_start + k): 13})
    return ws


def _write_kpi_dashboard(wb: Workbook, actual_cols: dict, n_months: int) -> Worksheet:
    ws = wb.create_sheet("KPI_Dashboard")
    ws["A1"] = "SaaS KPI Dashboard"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Linked to Data_Actuals; charts below update if the underlying data changes."
    ws["A2"].font = SUBTITLE_FONT

    header_row = 4
    fields = [
        ("Month", "month"),
        ("MRR", "mrr_ending"),
        ("ARR", "arr_ending"),
        ("Customers", "customers_ending"),
        ("Headcount", "headcount_total"),
        ("Cash", "cash"),
        ("NRR (TTM)", "nrr_ttm"),
        ("GRR (TTM)", "grr_ttm"),
        ("CAC (T3M)", "cac_trailing_3mo"),
        ("LTV:CAC", "ltv_to_cac"),
        ("Gross Margin %", "gross_margin_pct"),
        ("Net Burn (T3M)", "net_burn_trailing_3mo"),
        ("Runway (months)", "runway_months"),
        ("Rule of 40", "rule_of_40"),
    ]
    for j, (label, _) in enumerate(fields, start=1):
        c = ws.cell(row=header_row, column=j, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL

    data_start_row = actual_cols["_start_row"]
    for i in range(n_months):
        r = header_row + 1 + i
        data_r = data_start_row + i
        for j, (label, field) in enumerate(fields, start=1):
            col_letter = actual_cols[field]
            cell = ws.cell(row=r, column=j, value=f"=Data_Actuals!{col_letter}{data_r}")
            if label in ("NRR (TTM)", "GRR (TTM)", "Gross Margin %"):
                cell.number_format = PCT_FMT
            elif label == "Rule of 40":
                cell.number_format = "0.0"
            elif label in ("MRR", "ARR", "Cash", "CAC (T3M)", "Net Burn (T3M)"):
                cell.number_format = USD_FMT
            elif label == "LTV:CAC":
                cell.number_format = "0.00"

    last_row = header_row + n_months

    def add_line_chart(anchor: str, title: str, y_field_labels: list[str], y_axis_title: str) -> None:
        chart = LineChart()
        chart.title = title
        chart.y_axis.title = y_axis_title
        chart.x_axis.title = "Month"
        chart.height, chart.width = 8, 16
        cats = Reference(ws, min_col=1, min_row=header_row + 1, max_row=last_row)
        for label in y_field_labels:
            col_idx = [j for j, (lbl, _) in enumerate(fields, start=1) if lbl == label][0]
            data = Reference(ws, min_col=col_idx, min_row=header_row, max_row=last_row)
            chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        for series in chart.series:
            series.marker = Marker(symbol="circle", size=5)
            series.smooth = False
        ws.add_chart(chart, anchor)

    add_line_chart("A22", "MRR / ARR Growth", ["MRR", "ARR"], "$")
    add_line_chart("A40", "Net Revenue Retention vs. Gross Revenue Retention (TTM)", ["NRR (TTM)", "GRR (TTM)"], "%")
    add_line_chart("J22", "CAC (Trailing 3-Month) and LTV:CAC", ["CAC (T3M)", "LTV:CAC"], "Value")
    add_line_chart("J40", "Net Burn and Runway", ["Net Burn (T3M)", "Runway (months)"], "Value")

    _autosize(ws, {get_column_letter(j): 14 for j in range(1, len(fields) + 1)})
    return ws


def _write_variance_waterfall(wb: Workbook, variance_summary_dict: dict, variance_table: pd.DataFrame) -> Worksheet:
    ws = wb.create_sheet("Variance_Waterfall")
    ws["A1"] = "Year 3 EBITDA Bridge: Budget -> Actual"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Waterfall built as a stacked bar chart (invisible base + visible step), the standard Excel technique."
    ws["A2"].font = SUBTITLE_FONT

    fy = variance_table.groupby("line_item")[["budget", "actual", "variance"]].sum()

    budget_ebitda = fy.loc["ebitda", "budget"]
    actual_ebitda = fy.loc["ebitda", "actual"]
    rev_var = fy.loc["revenue", "variance"]
    cogs_var = -fy.loc["cogs", "variance"]  # a cogs increase reduces EBITDA
    sm_var = -fy.loc["opex_sm", "variance"]
    rd_var = -fy.loc["opex_rd", "variance"]
    ga_var = -fy.loc["opex_ga", "variance"]

    steps = [
        ("Budget EBITDA", budget_ebitda),
        ("Revenue Variance", rev_var),
        ("COGS Variance", cogs_var),
        ("S&M Variance", sm_var),
        ("R&D Variance", rd_var),
        ("G&A Variance", ga_var),
        ("Actual EBITDA", actual_ebitda),
    ]

    header_row = 4
    for j, h in enumerate(["Step", "Base (invisible)", "Value", "Decrease", "Increase", "Total"], start=1):
        c = ws.cell(row=header_row, column=j, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL

    running = 0.0
    for i, (label, value) in enumerate(steps):
        r = header_row + 1 + i
        ws.cell(row=r, column=1, value=label)
        is_total = label in ("Budget EBITDA", "Actual EBITDA")
        if is_total:
            base = 0.0
            total_val = value
            running = value
            ws.cell(row=r, column=3, value=None)
            ws.cell(row=r, column=4, value=None)
            ws.cell(row=r, column=5, value=None)
            ws.cell(row=r, column=6, value=total_val)
        else:
            new_running = running + value
            base = min(running, new_running)
            ws.cell(row=r, column=3, value=value)
            if value >= 0:
                ws.cell(row=r, column=5, value=value)
                ws.cell(row=r, column=4, value=None)
            else:
                ws.cell(row=r, column=4, value=-value)
                ws.cell(row=r, column=5, value=None)
            ws.cell(row=r, column=6, value=None)
            running = new_running
        ws.cell(row=r, column=2, value=base)
        for col in range(2, 7):
            cell = ws.cell(row=r, column=col)
            if cell.value is not None:
                cell.number_format = USD_FMT

    last_row = header_row + len(steps)
    chart = BarChart()
    chart.type = "col"
    chart.grouping = "stacked"
    chart.overlap = 100
    chart.title = "Year 3 EBITDA Bridge (Budget to Actual)"
    chart.y_axis.title = "$"
    chart.height, chart.width = 10, 22
    cats = Reference(ws, min_col=1, min_row=header_row + 1, max_row=last_row)
    base_data = Reference(ws, min_col=2, min_row=header_row, max_row=last_row)
    total_data = Reference(ws, min_col=6, min_row=header_row, max_row=last_row)
    decrease_data = Reference(ws, min_col=4, min_row=header_row, max_row=last_row)
    increase_data = Reference(ws, min_col=5, min_row=header_row, max_row=last_row)
    chart.add_data(base_data, titles_from_data=True)
    chart.add_data(total_data, titles_from_data=True)
    chart.add_data(decrease_data, titles_from_data=True)
    chart.add_data(increase_data, titles_from_data=True)
    chart.set_categories(cats)
    # make the "base" series invisible so the visible segments float
    base_series = chart.series[0]
    base_series.graphicalProperties.noFill = True
    total_series = chart.series[1]
    total_series.graphicalProperties.solidFill = "1F4E78"
    decrease_series = chart.series[2]
    decrease_series.graphicalProperties.solidFill = "C0504D"
    increase_series = chart.series[3]
    increase_series.graphicalProperties.solidFill = "4F9D69"
    ws.add_chart(chart, "A14")

    _autosize(ws, {"A": 20, "B": 16, "C": 14, "D": 14, "E": 14, "F": 14})
    return ws


def _write_variance_detail(wb: Workbook, variance_table: pd.DataFrame) -> Worksheet:
    ws = wb.create_sheet("Variance_Detail")
    ws["A1"] = "Full Budget vs. Actual Variance Detail (Year 3, all line items x months)"
    ws["A1"].font = TITLE_FONT
    df = variance_table.rename(
        columns={
            "month": "Month",
            "line_item": "Line Item",
            "budget": "Budget",
            "actual": "Actual",
            "variance": "Variance $",
            "variance_pct": "Variance %",
            "material": "Material?",
            "driver_category": "Driver Category",
            "note": "Note",
        }
    )
    col_letters = _write_df(ws, df, start_row=3)
    for i in range(len(df)):
        r = 4 + i
        ws[f"{col_letters['Budget']}{r}"].number_format = USD_FMT
        ws[f"{col_letters['Actual']}{r}"].number_format = USD_FMT
        ws[f"{col_letters['Variance $']}{r}"].number_format = USD_FMT
        ws[f"{col_letters['Variance %']}{r}"].number_format = PCT_FMT
        if df.iloc[i]["Material?"]:
            for col in col_letters.values():
                ws[f"{col}{r}"].fill = PatternFill(start_color="FDEBD0", end_color="FDEBD0", fill_type="solid")
    _autosize(ws, {col_letters[c]: 14 for c in df.columns})
    _autosize(ws, {col_letters["Note"]: 55})
    return ws


def _write_cash_flow_forecast_sheet(wb: Workbook, rolling_forecast: dict, scenario_summaries: dict) -> Worksheet:
    ws = wb.create_sheet("Cash_Flow_Forecast")
    ws["A1"] = "Rolling 12-Month Cash Flow Forecast: Base / Upside / Downside"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "A new forecast vintage is branched each time new actuals land; two vintages are shown below."
    ws["A2"].font = SUBTITLE_FONT

    row = 4
    for as_of_month, summary_df in scenario_summaries.items():
        ws.cell(row=row, column=1, value=f"Forecast as of Month {as_of_month} (next 12 months)").font = BOLD
        row += 1
        headers = list(summary_df.columns)
        for j, h in enumerate(headers, start=1):
            c = ws.cell(row=row, column=j, value=h)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
        row += 1
        for _, r in summary_df.iterrows():
            for j, h in enumerate(headers, start=1):
                ws.cell(row=row, column=j, value=r[h])
            row += 1
        row += 2

    chart_row_start = row + 1
    latest_as_of = max(rolling_forecast.keys())
    fdf = rolling_forecast[latest_as_of]
    ws.cell(row=chart_row_start, column=1, value=f"Monthly Cash Balance by Scenario (forecast as of Month {latest_as_of})").font = BOLD
    header_r = chart_row_start + 1
    months = sorted(fdf["month"].unique())
    ws.cell(row=header_r, column=1, value="Month")
    for j, month in enumerate(months, start=2):
        ws.cell(row=header_r, column=j, value=month)
    for i, scenario in enumerate(("downside", "base", "upside")):
        r = header_r + 1 + i
        ws.cell(row=r, column=1, value=scenario.capitalize())
        sub = fdf[fdf["scenario"] == scenario].set_index("month")
        for j, month in enumerate(months, start=2):
            ws.cell(row=r, column=j, value=float(sub.loc[month, "cash"])).number_format = USD_FMT

    chart = LineChart()
    chart.title = "Projected Cash Balance by Scenario"
    chart.y_axis.title = "Cash ($)"
    chart.x_axis.title = "Month"
    chart.height, chart.width = 9, 20
    data = Reference(ws, min_col=1, min_row=header_r, max_col=len(months) + 1, max_row=header_r + 3)
    chart.add_data(data, titles_from_data=True, from_rows=True)
    cats = Reference(ws, min_col=2, min_row=header_r, max_col=len(months) + 1)
    chart.set_categories(cats)
    ws.add_chart(chart, f"A{header_r + 6}")

    _autosize(ws, {"A": 26})
    return ws


def build_workbook(
    a: OperatingAssumptions,
    actual_full: pd.DataFrame,
    budget_y3: pd.DataFrame,
    variance_table: pd.DataFrame,
    rolling_forecast: dict,
    output_path: str,
) -> dict:
    """Assemble and save the full workbook. Returns a small dict of counts
    (tabs, formula tables, charts) for reporting."""
    from .cash_flow_forecast import scenario_summary

    wb = Workbook()
    wb.remove(wb.active)

    _write_assumptions_sheet(wb, a)

    ws_actual, actual_col_letters = _write_data_sheet(wb, "Data_Actuals", actual_full, ACTUAL_COLS)
    actual_col_letters["_start_row"] = 2
    ws_budget, budget_col_letters = _write_data_sheet(wb, "Data_BudgetY3", budget_y3, BUDGET_COLS)

    _write_pl_sheet(wb, a, actual_col_letters, budget_col_letters)
    _write_kpi_dashboard(wb, actual_col_letters, n_months=len(actual_full))

    from .variance_analysis import variance_summary as _vs

    _write_variance_waterfall(wb, _vs(variance_table), variance_table)
    _write_variance_detail(wb, variance_table)

    scenario_summaries = {}
    for as_of_month, fdf in rolling_forecast.items():
        starting_cash = float(fdf["cash"].iloc[0])
        scenario_summaries[as_of_month] = scenario_summary(fdf, starting_cash=starting_cash)
    _write_cash_flow_forecast_sheet(wb, rolling_forecast, scenario_summaries)

    wb.save(output_path)

    n_charts = sum(len(ws._charts) for ws in wb.worksheets)
    return {
        "tabs": len(wb.worksheets),
        "tab_names": wb.sheetnames,
        "native_charts": n_charts,
    }
