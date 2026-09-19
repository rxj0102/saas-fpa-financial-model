from saas_fpa.assumptions import OperatingAssumptions
from saas_fpa.budget_builder import build_year3_budget
from saas_fpa.variance_analysis import build_variance_table, simulate_year3_actuals, variance_summary


def _variance_table():
    a = OperatingAssumptions()
    _, budget, state24 = build_year3_budget(a)
    actual, _ = simulate_year3_actuals(a, state24)
    return build_variance_table(budget, actual, a), a, budget, actual


def test_actuals_branch_from_true_month24_state_not_the_budget_path():
    """Regression test for a state-aliasing bug: the noisy actuals run must
    start from the real month-24 exit point, not from wherever the budget
    run (which shares the same simulation engine) ended up after
    continuing 12 more months on that same mutable state object."""
    vt, a, budget, actual = _variance_table()
    rev = vt[vt["line_item"] == "revenue"]
    # With modest driver noise, no single month's revenue should differ by
    # more than ~40% from budget; a state-aliasing bug previously produced
    # a ~50% variance on cumulative Year 3 revenue.
    assert rev["variance_pct"].abs().max() < 0.4


def test_variance_table_row_count_matches_months_times_line_items():
    vt, a, budget, actual = _variance_table()
    n_months = a.budget_year_end_month - a.budget_year_start_month + 1
    from saas_fpa.variance_analysis import LINE_ITEMS

    assert len(vt) == n_months * len(LINE_ITEMS)


def test_variance_dollar_and_pct_are_consistent():
    vt, *_ = _variance_table()
    computed_variance = vt["actual"] - vt["budget"]
    assert (computed_variance.round(2) == vt["variance"].round(2)).all()


def test_materiality_requires_both_thresholds():
    vt, a, *_ = _variance_table()
    material = vt[vt["material"]]
    assert (material["variance"].abs() > a.materiality_threshold_abs).all()
    assert (material["variance_pct"].abs() > a.materiality_threshold_pct).all()


def test_summary_totals_are_internally_consistent():
    vt, *_ = _variance_table()
    summary = variance_summary(vt)
    assert abs(summary["total_revenue_variance"] - (summary["total_revenue_actual"] - summary["total_revenue_budget"])) < 1.0
    assert abs(summary["total_opex_variance"] - (summary["total_opex_actual"] - summary["total_opex_budget"])) < 1.0


def test_q2_push_month_shows_bookings_beat_and_sm_overspend():
    """The scripted Q2 paid-acquisition-push event should show up as both
    an S&M overspend and a new-bookings beat in the same month."""
    vt, a, *_ = _variance_table()
    push_month = a.budget_year_start_month + 3
    sm_row = vt[(vt["month"] == push_month) & (vt["line_item"] == "opex_sm")].iloc[0]
    bookings_row = vt[(vt["month"] == push_month) & (vt["line_item"] == "new_bookings_arr")].iloc[0]
    assert sm_row["variance"] > 0
    assert bookings_row["variance"] > 0
