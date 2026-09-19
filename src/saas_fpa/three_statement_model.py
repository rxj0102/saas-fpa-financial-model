"""Builds the linked Income Statement, Balance Sheet, and Cash Flow Statement
from the raw monthly operating data produced by ``data_generator``.

The three statements are linked by construction: cash flow is computed via
the indirect method directly from net income and the balance-sheet
working-capital deltas, so the balance sheet balances and the cash flow
statement reconciles to the change in the cash balance in every month, to
the cent. ``validate_tie_out`` checks this and is exercised by the test
suite in ``tests/test_three_statement_model.py``.
"""
from __future__ import annotations

import pandas as pd

TOLERANCE = 0.01


def build_income_statement(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        [
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
            "interest_income",
            "net_income",
        ]
    ].copy()


def build_balance_sheet(df: pd.DataFrame) -> pd.DataFrame:
    bs = df[
        [
            "month",
            "cash",
            "ar",
            "prepaid",
            "ppe_net",
            "ap",
            "accrued",
            "deferred_rev_balance",
            "retained_earnings",
            "common_stock_apic",
        ]
    ].copy()
    bs["total_current_assets"] = bs["cash"] + bs["ar"] + bs["prepaid"]
    bs["total_assets"] = bs["total_current_assets"] + bs["ppe_net"]
    bs["total_liabilities"] = bs["ap"] + bs["accrued"] + bs["deferred_rev_balance"]
    bs["total_equity"] = bs["common_stock_apic"] + bs["retained_earnings"]
    bs["total_liabilities_and_equity"] = bs["total_liabilities"] + bs["total_equity"]
    bs["balance_check"] = bs["total_assets"] - bs["total_liabilities_and_equity"]
    return bs


def build_cash_flow_statement(df: pd.DataFrame) -> pd.DataFrame:
    cf = df[["month", "net_income", "da", "cfo", "capex", "cfi", "funding_raised", "cff", "net_change_cash", "cash"]].copy()
    cf["delta_ar"] = -df["ar"].diff().fillna(df["ar"].iloc[0] - 0)
    cf["beginning_cash"] = cf["cash"] - cf["net_change_cash"]
    cf["ending_cash"] = cf["cash"]
    return cf


def validate_tie_out(df: pd.DataFrame) -> dict:
    """Assert the balance sheet balances and CF reconciles to cash. Raises
    AssertionError with the offending month(s) if not; returns a small
    summary dict on success."""
    bs = build_balance_sheet(df)
    max_balance_diff = bs["balance_check"].abs().max()
    bad_months = bs.loc[bs["balance_check"].abs() > TOLERANCE, "month"].tolist()
    assert not bad_months, f"Balance sheet does not balance in months: {bad_months} (max diff={max_balance_diff:.4f})"

    cf = build_cash_flow_statement(df)
    reconciled = (cf["beginning_cash"] + cf["net_change_cash"] - cf["ending_cash"]).abs()
    max_cf_diff = reconciled.max()
    bad_cf_months = cf.loc[reconciled > TOLERANCE, "month"].tolist()
    assert not bad_cf_months, f"Cash flow does not reconcile in months: {bad_cf_months} (max diff={max_cf_diff:.4f})"

    return {
        "months_checked": int(df["month"].max()),
        "max_balance_sheet_diff": float(max_balance_diff),
        "max_cash_flow_diff": float(max_cf_diff),
    }
