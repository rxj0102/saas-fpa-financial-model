"""Synthetic monthly SaaS operating-data generator.

Simulates, month by month, the operating engine of an early-stage SaaS
company: the customer/MRR waterfall (new, expansion, contraction, churned),
headcount by department, opex, capex, and the balance-sheet working-capital
accounts needed to build a linked three-statement model.

The simulation is deterministic given a set of :class:`~saas_fpa.assumptions.
OperatingAssumptions` and an optional ``noise_fn`` used only when generating
a noisy "actual" run to compare against a budget (see ``variance_analysis.py``).

Revenue recognition simplification: monthly recognized revenue is treated as
equal to ending MRR for the month. This is a standard simplification for a
monthly-billed SaaS business and is documented here rather than buried.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd

from .assumptions import OperatingAssumptions

NoiseFn = Callable[[int, np.random.Generator], dict]


@dataclass
class SimState:
    """Carries all balances that must persist from one month to the next."""

    customers: int
    mrr: float
    cash: float
    ar: float
    prepaid: float
    ap: float
    accrued: float
    ppe_net: float
    cumulative_capex: float
    deferred_rev_balance: float
    retained_earnings: float
    common_stock_apic: float
    deferred_rev_queue: list = field(default_factory=list)  # list of [remaining_months, monthly_amort]
    headcount: dict = field(default_factory=dict)  # {"S&M": int, "R&D": int, "G&A": int}


def _headcount_for_arr(plan, arr: float) -> dict:
    target = plan[0][1]
    for threshold, heads in plan:
        if arr >= threshold:
            target = heads
    return {"S&M": target[0], "R&D": target[1], "G&A": target[2]}


def initial_state(a: OperatingAssumptions) -> SimState:
    mrr0 = a.starting_customers * a.starting_avg_monthly_revenue_per_customer
    ar0 = mrr0 * (1 - a.pct_customers_annual_prepay) * a.dso_days / 30.0
    assets0 = a.starting_cash + ar0
    liab0 = 0.0
    retained_earnings0 = 0.0
    common_stock_apic0 = assets0 - liab0 - retained_earnings0
    return SimState(
        customers=a.starting_customers,
        mrr=mrr0,
        cash=a.starting_cash,
        ar=ar0,
        prepaid=0.0,
        ap=0.0,
        accrued=0.0,
        ppe_net=0.0,
        cumulative_capex=0.0,
        deferred_rev_balance=0.0,
        deferred_rev_queue=[],
        retained_earnings=retained_earnings0,
        common_stock_apic=common_stock_apic0,
        headcount=_headcount_for_arr(a.headcount_plan, mrr0 * 12),
    )


def _default_mults() -> dict:
    return {
        "growth": 1.0,
        "churn": 1.0,
        "expansion": 1.0,
        "contraction": 1.0,
        "acv": 1.0,
        "program_spend": 1.0,
        "other_opex": 1.0,
        "delay_hiring": False,
    }


def run_months(
    a: OperatingAssumptions,
    months: range,
    state: SimState,
    noise_fn: Optional[NoiseFn] = None,
    rng: Optional[np.random.Generator] = None,
    capture_at: Optional[set] = None,
) -> tuple[pd.DataFrame, SimState, dict]:
    """Simulate the given month numbers in sequence, continuing from ``state``.

    ``months`` must be a contiguous, increasing range. ``state`` is mutated
    in place; the function also returns it for convenience. Returns
    ``(df, state, snapshots)`` where ``df`` has one row per simulated month
    and ``snapshots`` is a ``{month: SimState}`` dict of deep-copied state
    for every month in ``capture_at`` (used by the rolling forecast to
    branch a forecast from a specific point in the realized history).
    """
    import copy as _copy

    rows = []
    snapshots: dict = {}
    for t in months:
        mults = _default_mults()
        if noise_fn is not None:
            mults.update(noise_fn(t, rng))

        mrr_beginning = state.mrr
        customers_beginning = state.customers
        avg_customer_mrr = (mrr_beginning / customers_beginning) if customers_beginning else 0.0

        churn_rate = a.interp(a.logo_churn_rate_start, a.logo_churn_rate_end, t) * mults["churn"]
        expansion_rate = a.interp(a.monthly_expansion_rate_start, a.monthly_expansion_rate_end, t) * mults["expansion"]
        contraction_rate = a.interp(a.monthly_contraction_rate_start, a.monthly_contraction_rate_end, t) * mults["contraction"]
        growth_rate = a.interp(a.new_bookings_growth_rate_start, a.new_bookings_growth_rate_end, t) * mults["growth"]
        new_acv = a.interp(a.starting_new_customer_acv, a.ending_new_customer_acv, t) * mults["acv"]
        cogs_pct = a.interp(a.cogs_pct_of_revenue_start, a.cogs_pct_of_revenue_end, t)
        sales_cycle_days = a.interp(a.sales_cycle_days_start, a.sales_cycle_days_end, t)
        rd_other_opex = a.interp(a.rd_other_opex_monthly_start, a.rd_other_opex_monthly_end, t) * mults["other_opex"]
        ga_other_opex = a.interp(a.ga_other_opex_monthly_start, a.ga_other_opex_monthly_end, t) * mults["other_opex"]

        customers_churned = round(customers_beginning * churn_rate)
        mrr_churned = customers_beginning * churn_rate * avg_customer_mrr
        mrr_expansion = mrr_beginning * expansion_rate
        mrr_contraction = mrr_beginning * contraction_rate

        target_new_mrr = mrr_beginning * growth_rate
        new_customers = max(0, round(target_new_mrr / (new_acv / 12.0))) if new_acv > 0 else 0
        mrr_new = new_customers * (new_acv / 12.0)

        mrr_ending = mrr_beginning - mrr_churned + mrr_expansion - mrr_contraction + mrr_new
        customers_ending = customers_beginning - customers_churned + new_customers

        revenue = mrr_ending
        cogs = revenue * cogs_pct
        new_bookings_arr = mrr_new * 12.0

        arr_trailing = mrr_beginning * 12.0
        target_headcount = _headcount_for_arr(a.headcount_plan, arr_trailing)
        new_headcount = {}
        for dept, target in target_headcount.items():
            current = state.headcount.get(dept, target)
            if mults["delay_hiring"] and target > current:
                new_headcount[dept] = current
            else:
                new_headcount[dept] = target
        state.headcount = new_headcount

        payroll = {d: state.headcount[d] * a.avg_fully_loaded_monthly_cost[d] for d in ("S&M", "R&D", "G&A")}
        sm_program_spend = a.sm_program_spend_pct_of_new_bookings_arr * new_bookings_arr * mults["program_spend"]

        opex_sm = payroll["S&M"] + sm_program_spend
        opex_rd = payroll["R&D"] + rd_other_opex
        opex_ga = payroll["G&A"] + ga_other_opex
        total_opex = opex_sm + opex_rd + opex_ga

        capex = a.monthly_capex
        state.cumulative_capex += capex
        da = state.cumulative_capex / a.ppe_useful_life_months
        ppe_net = state.ppe_net + capex - da

        gross_profit = revenue - cogs
        ebitda = gross_profit - total_opex
        ebit = ebitda - da
        interest_income = state.cash * 0.04 / 12.0
        net_income = ebit + interest_income

        monthly_billed_revenue = revenue * (1 - a.pct_customers_annual_prepay)
        ar = monthly_billed_revenue * a.dso_days / 30.0
        prepaid = a.prepaid_pct_of_opex * total_opex
        ap = (cogs + total_opex) * a.dpo_days / 30.0
        accrued = a.accrued_payroll_fraction * sum(payroll.values())

        annual_prepay_new_mrr = mrr_new * a.pct_customers_annual_prepay
        net_deferred_addition = annual_prepay_new_mrr * 11.0
        if net_deferred_addition > 0:
            state.deferred_rev_queue.append([11, net_deferred_addition / 11.0])
        amortization = 0.0
        remaining_queue = []
        for remaining, monthly_amt in state.deferred_rev_queue:
            amortization += monthly_amt
            if remaining - 1 > 0:
                remaining_queue.append([remaining - 1, monthly_amt])
        state.deferred_rev_queue = remaining_queue
        deferred_rev_balance = state.deferred_rev_balance + net_deferred_addition - amortization

        delta_ar = ar - state.ar
        delta_prepaid = prepaid - state.prepaid
        delta_ap = ap - state.ap
        delta_accrued = accrued - state.accrued
        delta_deferred = deferred_rev_balance - state.deferred_rev_balance

        cfo = net_income + da - delta_ar - delta_prepaid + delta_ap + delta_accrued + delta_deferred
        cfi = -capex
        funding_raised = sum(amt for m, amt, _ in a.funding_events if m == t)
        cff = funding_raised
        net_change_cash = cfo + cfi + cff
        cash = state.cash + net_change_cash

        retained_earnings = state.retained_earnings + net_income
        common_stock_apic = state.common_stock_apic + funding_raised

        rows.append(
            dict(
                month=t,
                customers_beginning=customers_beginning,
                customers_new=new_customers,
                customers_churned=customers_churned,
                customers_ending=customers_ending,
                mrr_beginning=mrr_beginning,
                mrr_new=mrr_new,
                mrr_expansion=mrr_expansion,
                mrr_contraction=mrr_contraction,
                mrr_churned=mrr_churned,
                mrr_ending=mrr_ending,
                arr_ending=mrr_ending * 12.0,
                revenue=revenue,
                cogs=cogs,
                gross_profit=gross_profit,
                headcount_sm=state.headcount["S&M"],
                headcount_rd=state.headcount["R&D"],
                headcount_ga=state.headcount["G&A"],
                headcount_total=sum(state.headcount.values()),
                payroll_sm=payroll["S&M"],
                payroll_rd=payroll["R&D"],
                payroll_ga=payroll["G&A"],
                sm_program_spend=sm_program_spend,
                opex_sm=opex_sm,
                opex_rd=opex_rd,
                opex_ga=opex_ga,
                total_opex=total_opex,
                ebitda=ebitda,
                da=da,
                ebit=ebit,
                interest_income=interest_income,
                net_income=net_income,
                capex=capex,
                ppe_net=ppe_net,
                ar=ar,
                prepaid=prepaid,
                ap=ap,
                accrued=accrued,
                deferred_rev_balance=deferred_rev_balance,
                cash=cash,
                retained_earnings=retained_earnings,
                common_stock_apic=common_stock_apic,
                funding_raised=funding_raised,
                new_bookings_arr=new_bookings_arr,
                new_customer_acv=new_acv,
                churn_rate=churn_rate,
                expansion_rate=expansion_rate,
                contraction_rate=contraction_rate,
                growth_rate=growth_rate,
                cogs_pct=cogs_pct,
                sales_cycle_days=sales_cycle_days,
                cfo=cfo,
                cfi=cfi,
                cff=cff,
                net_change_cash=net_change_cash,
            )
        )

        state.mrr = mrr_ending
        state.customers = customers_ending
        state.cash = cash
        state.ar = ar
        state.prepaid = prepaid
        state.ap = ap
        state.accrued = accrued
        state.ppe_net = ppe_net
        state.deferred_rev_balance = deferred_rev_balance
        state.retained_earnings = retained_earnings
        state.common_stock_apic = common_stock_apic

        if capture_at and t in capture_at:
            snapshots[t] = _copy.deepcopy(state)

    return pd.DataFrame(rows), state, snapshots


def generate_history(a: OperatingAssumptions) -> pd.DataFrame:
    """Generate the full deterministic 1..n_months operating history.

    This deterministic run doubles as both the historical "actuals" for
    months 1-24 and the Year 3 "budget" for months 25-36 (see
    ``budget_builder.py``).
    """
    state = initial_state(a)
    df, _, _ = run_months(a, range(1, a.n_months + 1), state, noise_fn=None)
    return df
