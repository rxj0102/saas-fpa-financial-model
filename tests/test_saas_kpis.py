from saas_fpa.assumptions import OperatingAssumptions
from saas_fpa.data_generator import generate_history
from saas_fpa.saas_kpis import compute_kpis, kpi_snapshot


def _kpis():
    a = OperatingAssumptions()
    df = generate_history(a)
    return compute_kpis(df)


def test_grr_never_exceeds_nrr():
    k = _kpis()
    valid = k.dropna(subset=["nrr_monthly", "grr_monthly"])
    assert (valid["nrr_monthly"] >= valid["grr_monthly"] - 1e-9).all()


def test_grr_never_exceeds_100_pct():
    k = _kpis()
    assert (k["grr_monthly"].dropna() <= 1.0 + 1e-9).all()


def test_gross_margin_between_0_and_1():
    k = _kpis()
    gm = k["gross_margin_pct"].dropna()
    assert (gm > 0).all() and (gm < 1).all()


def test_ltv_to_cac_is_positive_and_finite_where_defined():
    k = _kpis()
    vals = k["ltv_to_cac"].dropna()
    assert (vals > 0).all()
    assert (vals < 100).all()  # sanity bound, not a real ceiling


def test_runway_is_positive_while_cash_is_positive():
    k = _kpis()
    positive_cash = k[k["cash"] > 0]
    assert (positive_cash["runway_months"] > 0).all()


def test_kpi_snapshot_returns_expected_keys():
    k = _kpis()
    snap = kpi_snapshot(k, 36)
    for key in ("mrr", "arr", "nrr_ttm", "grr_ttm", "cac_trailing_3mo", "ltv_to_cac", "rule_of_40"):
        assert key in snap
