"""Single source of truth for every operating driver used in the model.

Every other module (data generation, the three-statement model, the budget
build, the forecast) reads its numbers from an :class:`OperatingAssumptions`
instance instead of hardcoding them. Change a driver here and it flows
through the whole pipeline.

Company profile modeled: an early-stage, SMB self-serve + inside-sales SaaS
company starting around $500K ARR and growing to roughly $1.8-2.0M ARR over
36 months.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class OperatingAssumptions:
    """All operating, financial, and scenario drivers for the model."""

    # --- Time horizon ---
    n_months: int = 36
    start_date: date = date(2023, 1, 1)

    # --- Starting position (Month 1) ---
    starting_customers: int = 96
    starting_avg_monthly_revenue_per_customer: float = 416.67  # ~$5,000 ACV
    starting_cash: float = 2_500_000.0

    # --- Growth engine: target new-bookings MRR as a % of trailing MRR,
    # decelerating over the horizon (classic SaaS growth-curve deceleration
    # as the revenue base gets larger).
    new_bookings_growth_rate_start: float = 0.072
    new_bookings_growth_rate_end: float = 0.022

    # New-customer ACV drifts up as the company moves slightly up-market.
    starting_new_customer_acv: float = 5_000.0
    ending_new_customer_acv: float = 6_200.0

    # --- Retention drivers (apply only to the existing customer base;
    # new bookings are tracked separately so NRR/GRR are computed correctly).
    logo_churn_rate_start: float = 0.014
    logo_churn_rate_end: float = 0.009
    monthly_expansion_rate_start: float = 0.010
    monthly_expansion_rate_end: float = 0.018
    monthly_contraction_rate_start: float = 0.004
    monthly_contraction_rate_end: float = 0.0025

    # --- Sales efficiency ---
    sales_cycle_days_start: float = 18.0
    sales_cycle_days_end: float = 27.0
    # Non-headcount S&M program/ad spend, as a % of the *annualized* value
    # of new bookings signed in the month. Combined with S&M headcount
    # cost this produces a fully-loaded CAC (CAC is always a derived KPI
    # here, never a hardcoded input).
    sm_program_spend_pct_of_new_bookings_arr: float = 0.20

    # --- COGS / gross margin ---
    cogs_pct_of_revenue_start: float = 0.25
    cogs_pct_of_revenue_end: float = 0.20

    # --- Headcount plan: hire waves triggered at ARR milestones.
    # Each tuple is (ARR milestone threshold, (S&M heads, R&D heads, G&A heads)).
    headcount_plan: tuple = (
        (0, (2, 6, 2)),
        (750_000, (2, 7, 3)),
        (1_000_000, (3, 8, 3)),
        (1_300_000, (3, 9, 4)),
        (1_600_000, (4, 11, 5)),
        (1_900_000, (4, 12, 6)),
        (2_200_000, (5, 14, 7)),
    )
    avg_fully_loaded_monthly_cost: dict = field(
        default_factory=lambda: {"S&M": 11_500.0, "R&D": 13_500.0, "G&A": 10_500.0}
    )

    # --- Other (non-headcount) departmental opex, linearly interpolated ---
    rd_other_opex_monthly_start: float = 6_000.0
    rd_other_opex_monthly_end: float = 14_000.0
    ga_other_opex_monthly_start: float = 8_000.0
    ga_other_opex_monthly_end: float = 22_000.0

    # --- Capex / PP&E ---
    monthly_capex: float = 2_500.0
    ppe_useful_life_months: int = 36

    # --- Working capital ---
    dso_days: float = 21.0
    dpo_days: float = 30.0
    pct_customers_annual_prepay: float = 0.18
    deferred_revenue_amortization_months: int = 12
    prepaid_pct_of_opex: float = 0.02
    accrued_payroll_fraction: float = 0.5

    # --- Financing events: (month, amount, label) ---
    funding_events: tuple = ((13, 3_500_000.0, "Series A"),)

    # --- Budget / variance analysis (Year 3 only, months 25-36) ---
    budget_year_start_month: int = 25
    budget_year_end_month: int = 36
    materiality_threshold_pct: float = 0.10
    materiality_threshold_abs: float = 5_000.0
    variance_random_seed: int = 42
    # Std. dev of noise applied to each driver when simulating "actuals"
    # against the Year 3 budget.
    noise_std_new_bookings_growth: float = 0.09   # relative std dev
    noise_std_churn: float = 0.12
    noise_std_acv: float = 0.03
    noise_std_program_spend: float = 0.12
    noise_std_other_opex: float = 0.08
    hiring_delay_prob: float = 0.20   # chance a planned hire slips a month
    hiring_delay_months: int = 1

    # --- Scenario multipliers for the rolling cash flow forecast ---
    upside_growth_multiplier: float = 1.25
    upside_churn_multiplier: float = 0.85
    downside_growth_multiplier: float = 0.70
    downside_churn_multiplier: float = 1.30

    def interp(self, start: float, end: float, month: int) -> float:
        """Linear interpolation of a drifting driver from month 1..n_months."""
        if self.n_months <= 1:
            return start
        frac = (month - 1) / (self.n_months - 1)
        return start + (end - start) * frac
