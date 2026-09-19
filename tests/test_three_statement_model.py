from saas_fpa.assumptions import OperatingAssumptions
from saas_fpa.data_generator import generate_history
from saas_fpa.three_statement_model import (
    build_balance_sheet,
    build_cash_flow_statement,
    build_income_statement,
    validate_tie_out,
)


def test_generates_full_horizon():
    a = OperatingAssumptions()
    df = generate_history(a)
    assert len(df) == a.n_months
    assert df["month"].tolist() == list(range(1, a.n_months + 1))


def test_balance_sheet_balances_every_month():
    a = OperatingAssumptions()
    df = generate_history(a)
    bs = build_balance_sheet(df)
    assert (bs["balance_check"].abs() < 0.01).all()


def test_cash_flow_reconciles_to_cash_balance():
    a = OperatingAssumptions()
    df = generate_history(a)
    cf = build_cash_flow_statement(df)
    diff = (cf["beginning_cash"] + cf["net_change_cash"] - cf["ending_cash"]).abs()
    assert (diff < 0.01).all()


def test_cash_never_goes_negative():
    a = OperatingAssumptions()
    df = generate_history(a)
    assert df["cash"].min() > 0, "model implies insolvency; funding events are undersized"


def test_validate_tie_out_helper_passes():
    a = OperatingAssumptions()
    df = generate_history(a)
    result = validate_tie_out(df)
    assert result["months_checked"] == a.n_months
    assert result["max_balance_sheet_diff"] < 0.01
    assert result["max_cash_flow_diff"] < 0.01


def test_income_statement_shape():
    a = OperatingAssumptions()
    df = generate_history(a)
    is_ = build_income_statement(df)
    assert (is_["gross_profit"] == is_["revenue"] - is_["cogs"]).all()
    assert (
        (is_["ebitda"] - (is_["gross_profit"] - is_["opex_sm"] - is_["opex_rd"] - is_["opex_ga"])).abs() < 0.01
    ).all()


def test_customer_and_mrr_counts_are_non_negative():
    a = OperatingAssumptions()
    df = generate_history(a)
    assert (df["customers_ending"] > 0).all()
    assert (df["mrr_ending"] > 0).all()
