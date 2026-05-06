# -*- coding: utf-8 -*-
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase

from biz_monthly_analytic_budget.models import purchase_order as purchase_order_module


class _FakeEngine:
    def __init__(self):
        self.reserve_calls = []
        self.consume_calls = []
        self.release_calls = []

    def reserve_budget(self, context):
        self.reserve_calls.append(context)

    def consume_budget(self, context):
        self.consume_calls.append(context)

    def release_budget(self, context):
        self.release_calls.append(context)


class _FakeBudgetLineModel:
    def __init__(self, budget_line):
        self.budget_line = budget_line
        self.lock_calls = []

    def _lock_budget_lines(self, analytic_ids, plan_id):
        self.lock_calls.append((tuple(analytic_ids), plan_id))

    def _find_budget_line(self, plan, dims, log_fallback=True):
        if dims.get('analytic_account_id') == self.budget_line.analytic_account_id.id:
            return [self.budget_line]
        return []


class _FakeAnalyticRecord:
    def __init__(self, analytic_id, name='AA'):
        self.id = analytic_id
        self.name = name
        self.display_name = name

    def exists(self):
        return True


class _FakeAnalyticModel:
    def __init__(self, record):
        self.record = record

    def browse(self, analytic_id):
        if analytic_id == self.record.id:
            return self.record
        return _FakeAnalyticRecord(analytic_id, name='Unknown')


class _FakeCommitmentModel:
    def __init__(self, search_result=False):
        self.search_result = search_result

    def sudo(self):
        return self

    def search(self, domain, limit=None, order=None):
        return self.search_result


class _FakeEnv:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


class _FakePO:
    def __init__(self, state, env, payment_date=date(2026, 4, 18)):
        self.state = state
        self.env = env
        self.payment_date = payment_date
        self.company_id = SimpleNamespace(id=1)
        self.order_line = [object()]
        self.id = 12
        self.name = 'PO-12'
        self._name = 'purchase.order'

    def ensure_one(self):
        return None

    def __iter__(self):
        yield self

    def _has_active_source_requisition_for_plan(self, plan):
        return False

    def _is_counted_in_monthly_budget_reserve(self, plan):
        return False

    def _get_budget_document_identity(self):
        return self._name, self.id


class TestPurchaseOrderMonthlyBudget(TransactionCase):

    def test_direct_po_reservation_skips_after_confirmation(self):
        engine = _FakeEngine()
        analytic = _FakeAnalyticRecord(10)
        budget_line = SimpleNamespace(
            analytic_account_id=analytic,
            budget_amount=100.0,
        )
        env = _FakeEnv({
            'monthly.budget.line': _FakeBudgetLineModel(budget_line),
            'budget.engine': engine,
            'account.analytic.account': _FakeAnalyticModel(analytic),
            'budget.commitment': _FakeCommitmentModel(False),
        })
        order = _FakePO(state='purchase', env=env)
        plan = SimpleNamespace(
            id=1,
            company_id=SimpleNamespace(id=1),
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            _refresh_budget_snapshot=Mock(),
        )

        with patch.object(purchase_order_module, 'find_active_monthly_plan', return_value=plan):
            with patch.object(
                purchase_order_module,
                'extract_analytic_amounts',
                return_value=[(10, 50.0)],
            ):
                with patch.object(
                    purchase_order_module,
                    'filter_analytic_totals_for_plan',
                    return_value=({10: 50.0}, {}),
                ):
                    purchase_order_module.PurchaseOrder._reserve_monthly_budget_for_direct_rfq(order)

        self.assertEqual(engine.reserve_calls, [])

    def test_direct_po_reservation_creates_commitment_before_confirmation(self):
        engine = _FakeEngine()
        analytic = _FakeAnalyticRecord(10)
        budget_line = SimpleNamespace(
            analytic_account_id=analytic,
            budget_amount=100.0,
        )
        env = _FakeEnv({
            'monthly.budget.line': _FakeBudgetLineModel(budget_line),
            'budget.engine': engine,
            'account.analytic.account': _FakeAnalyticModel(analytic),
            'budget.commitment': _FakeCommitmentModel(False),
        })
        order = _FakePO(state='draft', env=env)
        plan = SimpleNamespace(
            id=1,
            company_id=SimpleNamespace(id=1),
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            _refresh_budget_snapshot=Mock(),
        )

        with patch.object(purchase_order_module, 'find_active_monthly_plan', return_value=plan):
            with patch.object(
                purchase_order_module,
                'extract_analytic_amounts',
                return_value=[(10, 50.0)],
            ):
                with patch.object(
                    purchase_order_module,
                    'filter_analytic_totals_for_plan',
                    return_value=({10: 50.0}, {}),
                ):
                    purchase_order_module.PurchaseOrder._reserve_monthly_budget_for_direct_rfq(order)

        self.assertEqual(len(engine.reserve_calls), 1)
