import openpyxl
import pandas as pd
from openpyxl.utils import get_column_letter

from saas_fpa.assumptions import OperatingAssumptions
from saas_fpa.budget_builder import build_year3_budget
from saas_fpa.cash_flow_forecast import build_rolling_forecast
from saas_fpa.excel_report import ACTUAL_COLS, BUDGET_COLS, PL_LINE_ITEMS, build_workbook
from saas_fpa.saas_kpis import compute_kpis
from saas_fpa.variance_analysis import build_variance_table, simulate_year3_actuals

# LibreOffice is not functional in this sandbox (fails to load even a
# trivial workbook), so formulas can't be recalculated end-to-end here.
# These tests instead verify: (1) the workbook is well-formed OOXML that
# round-trips through openpyxl, (2) the raw data ported into Data_Actuals /
# Data_BudgetY3 exactly matches the source DataFrames (this is what the
# XLOOKUP formulas actually read), and (3) every formula cell references
# the correct month and column, so a real XLOOKUP evaluation would be
# correct by construction.


def _build(tmp_path):
    a = OperatingAssumptions()
    history, budget, state24 = build_year3_budget(a)
    actual_y3, snaps = simulate_year3_actuals(a, state24, capture_at={36})
    combined_actual = pd.concat([history, actual_y3], ignore_index=True)
    kpis = compute_kpis(combined_actual)
    vt = build_variance_table(budget, actual_y3, a)
    rolling = build_rolling_forecast(a, {24: state24, 36: snaps[36]}, n_months=12)
    out = tmp_path / "model.xlsx"
    result = build_workbook(a, kpis, budget, vt, rolling, str(out))
    return a, kpis, budget, vt, out, result


def test_workbook_has_expected_tabs_and_charts(tmp_path):
    a, kpis, budget, vt, out, result = _build(tmp_path)
    expected_tabs = {
        "Assumptions",
        "Data_Actuals",
        "Data_BudgetY3",
        "PL_Actual_vs_Budget",
        "KPI_Dashboard",
        "Variance_Waterfall",
        "Variance_Detail",
        "Cash_Flow_Forecast",
    }
    assert set(result["tab_names"]) == expected_tabs
    assert result["native_charts"] >= 5


def test_workbook_round_trips_through_openpyxl(tmp_path):
    _, _, _, _, out, _ = _build(tmp_path)
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames


def test_data_actuals_matches_source_dataframe_exactly(tmp_path):
    a, kpis, budget, vt, out, _ = _build(tmp_path)
    wb = openpyxl.load_workbook(out)
    ws = wb["Data_Actuals"]
    for i, col in enumerate(ACTUAL_COLS, start=1):
        header = ws.cell(row=1, column=i).value
        assert header == col
    # Spot-check several rows across the horizon for a couple of columns
    month_col_idx = ACTUAL_COLS.index("month") + 1
    revenue_col_idx = ACTUAL_COLS.index("revenue") + 1
    for row_offset in (0, 11, 23, 35):
        excel_row = row_offset + 2
        month = ws.cell(row=excel_row, column=month_col_idx).value
        revenue = ws.cell(row=excel_row, column=revenue_col_idx).value
        expected = kpis.iloc[row_offset]
        assert month == expected["month"]
        assert abs(revenue - expected["revenue"]) < 0.01


def test_data_budget_matches_source_dataframe_exactly(tmp_path):
    a, kpis, budget, vt, out, _ = _build(tmp_path)
    wb = openpyxl.load_workbook(out)
    ws = wb["Data_BudgetY3"]
    month_col_idx = BUDGET_COLS.index("month") + 1
    ebitda_col_idx = BUDGET_COLS.index("ebitda") + 1
    for row_offset in range(len(budget)):
        excel_row = row_offset + 2
        assert ws.cell(row=excel_row, column=month_col_idx).value == budget.iloc[row_offset]["month"]
        assert abs(ws.cell(row=excel_row, column=ebitda_col_idx).value - budget.iloc[row_offset]["ebitda"]) < 0.01


def test_pl_formulas_reference_correct_month_and_field(tmp_path):
    a, kpis, budget, vt, out, _ = _build(tmp_path)
    wb = openpyxl.load_workbook(out)
    ws = wb["PL_Actual_vs_Budget"]
    months = list(range(a.budget_year_start_month, a.budget_year_end_month + 1))
    first_data_row = 6
    for i, (label, field) in enumerate(PL_LINE_ITEMS):
        r = first_data_row + i
        for m_idx, m in enumerate(months):
            base_col = 2 + m_idx * 4
            actual_cell = ws.cell(row=r, column=base_col)
            budget_cell = ws.cell(row=r, column=base_col + 1)
            var_cell = ws.cell(row=r, column=base_col + 2)
            pct_cell = ws.cell(row=r, column=base_col + 3)
            expected_actual_col = get_column_letter(ACTUAL_COLS.index(field) + 1)
            expected_budget_col = get_column_letter(BUDGET_COLS.index(field) + 1)
            assert actual_cell.value == (
                f"=IFERROR(XLOOKUP({m},Data_Actuals!$A:$A,Data_Actuals!${expected_actual_col}:${expected_actual_col}),0)"
            )
            assert budget_cell.value == (
                f"=IFERROR(XLOOKUP({m},Data_BudgetY3!$A:$A,Data_BudgetY3!${expected_budget_col}:${expected_budget_col}),0)"
            )
            assert var_cell.value == f"={actual_cell.coordinate}-{budget_cell.coordinate}"
            assert pct_cell.value.startswith(f"=IF({budget_cell.coordinate}=0,0,{var_cell.coordinate}/ABS(")
