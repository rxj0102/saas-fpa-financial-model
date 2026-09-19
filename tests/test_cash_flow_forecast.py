from saas_fpa.assumptions import OperatingAssumptions
from saas_fpa.budget_builder import build_year3_budget
from saas_fpa.cash_flow_forecast import SCENARIOS, forecast_all_scenarios, scenario_summary


def test_forecast_has_all_three_scenarios_and_horizon():
    a = OperatingAssumptions()
    _, _, state24 = build_year3_budget(a)
    fdf = forecast_all_scenarios(a, state24, as_of_month=24, n_months=12)
    assert set(fdf["scenario"].unique()) == set(SCENARIOS)
    for scenario in SCENARIOS:
        months = fdf[fdf["scenario"] == scenario]["month"]
        assert months.tolist() == list(range(25, 37))


def test_upside_grows_faster_than_downside():
    a = OperatingAssumptions()
    _, _, state24 = build_year3_budget(a)
    fdf = forecast_all_scenarios(a, state24, as_of_month=24, n_months=12)
    upside_end_arr = fdf[fdf["scenario"] == "upside"]["arr_ending"].iloc[-1]
    base_end_arr = fdf[fdf["scenario"] == "base"]["arr_ending"].iloc[-1]
    downside_end_arr = fdf[fdf["scenario"] == "downside"]["arr_ending"].iloc[-1]
    assert upside_end_arr > base_end_arr > downside_end_arr


def test_scenario_summary_shape():
    a = OperatingAssumptions()
    _, _, state24 = build_year3_budget(a)
    fdf = forecast_all_scenarios(a, state24, as_of_month=24, n_months=12)
    summary = scenario_summary(fdf, starting_cash=float(state24.cash))
    assert len(summary) == 3
    assert set(summary["scenario"]) == set(SCENARIOS)
    assert (summary["min_cash"] <= summary["ending_cash"] + 1e-6).all()
