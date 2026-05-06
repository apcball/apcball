# -*- coding: utf-8 -*-
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase

from biz_monthly_analytic_budget.models import purchase_requisition as pr_module
from biz_monthly_analytic_budget.models import purchase_order as po_module


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


class _FakeCommitment:
    def __init__(self, state='reserved', amount=25.0, date_value=date(2026, 4, 18)):
        self.state = state
        self.amount = amount
        self.date = date_value
        self.write_calls = []
        self.action_release_calls = 0

    def write(self, vals):
        self.write_calls.append(vals)
        self.state = vals.get('state', self.state)
        self.amount = vals.get('amount', self.amount)
        self.date = vals.get('date', self.date)

    def action_release(self):
        self.action_release_calls += 1
        self.state = 'released'


class _FakeCommitmentModel:
    def __init__(self, search_result=False):
        self.search_result = search_result

    def sudo(self):
        return self

    def search(self, domain, limit=None, order=None):
        return self.search_result

    def search_count(self, domain):
        return 0


class _FakeEnv:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


class _FakePR:
    def __init__(self, env, state='draft', payment_date=date(2026, 4, 18)):
        self.env = env
        self.state = state
        self.payment_date = payment_date
        self.company_id = SimpleNamespace(id=1)
        self.requisition_order_ids = [object()]
        self.id = 21
        self.name = 'PR-21'
        self._name = 'employee.purchase.requisition'

    def ensure_one(self):
        return None

    def __iter__(self):
        yield self


class _FakePO:
    def __init__(self, env, state='draft', payment_date=date(2026, 4, 18)):
        self.env = env
        self.state = state
        self.payment_date = payment_date
        self.company_id = SimpleNamespace(id=1)
        self.order_line = [object()]
        self.id = 31
        self.name = 'PO-31'
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


class TestMonthlyBudgetLifecycle(TransactionCase):

    def test_pr_reserve_helper_creates_one_commitment(self):
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
        pr = _FakePR(env=env)
        plan = SimpleNamespace(
            id=1,
            company_id=SimpleNamespace(id=1),
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            _refresh_budget_snapshot=Mock(),
        )

        with patch.object(pr_module, 'find_active_monthly_plan', return_value=plan):
            with patch.object(
                pr_module,
                'extract_analytic_amounts',
                return_value=[(10, 75.0)],
            ):
                with patch.object(
                    pr_module,
                    'filter_analytic_totals_for_plan',
                    return_value=({10: 75.0}, {}),
                ):
                    pr_module.EmployeePurchaseRequisitionMonthly._reserve_monthly_analytic_budget(pr)

        self.assertEqual(len(engine.reserve_calls), 1)

    def test_pr_release_helper_releases_existing_commitment(self):
        engine = _FakeEngine()
        analytic = _FakeAnalyticRecord(10)
        budget_line = SimpleNamespace(
            analytic_account_id=analytic,
            budget_amount=100.0,
        )
        existing = _FakeCommitment()
        env = _FakeEnv({
            'monthly.budget.line': _FakeBudgetLineModel(budget_line),
            'budget.engine': engine,
            'account.analytic.account': _FakeAnalyticModel(analytic),
            'budget.commitment': _FakeCommitmentModel(existing),
        })
        pr = _FakePR(env=env)
        plan = SimpleNamespace(
            id=1,
            company_id=SimpleNamespace(id=1),
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            _refresh_budget_snapshot=Mock(),
        )

        with patch.object(pr_module, 'find_active_monthly_plan', return_value=plan):
            pr_module.EmployeePurchaseRequisitionMonthly._release_monthly_analytic_budget(pr)

        self.assertEqual(len(engine.release_calls), 1)

    def test_po_consume_helper_consumes_reserved_budget(self):
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
        po = _FakePO(env=env, state='draft')
        plan = SimpleNamespace(
            id=1,
            company_id=SimpleNamespace(id=1),
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            _refresh_budget_snapshot=Mock(),
        )

        with patch.object(po_module, 'find_active_monthly_plan', return_value=plan):
            with patch.object(
                po_module,
                'extract_analytic_amounts',
                return_value=[(10, 50.0)],
            ):
                with patch.object(
                    po_module,
                    'filter_analytic_totals_for_plan',
                    return_value=({10: 50.0}, {}),
                ):
                    po_module.PurchaseOrder._consume_monthly_analytic_budget(po)

        self.assertEqual(len(engine.consume_calls), 1)

    def test_po_cancel_helper_releases_consumed_budget(self):
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
        po = _FakePO(env=env, state='purchase')
        plan = SimpleNamespace(
            id=1,
            company_id=SimpleNamespace(id=1),
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            _refresh_budget_snapshot=Mock(),
        )

        with patch.object(po_module, 'find_active_monthly_plan', return_value=plan):
            with patch.object(
                po_module,
                'extract_analytic_amounts',
                return_value=[(10, 50.0)],
            ):
                with patch.object(
                    po_module,
                    'filter_analytic_totals_for_plan',
                    return_value=({10: 50.0}, {}),
                ):
                    po_module.PurchaseOrder._release_monthly_analytic_budget_on_cancel(po)

        self.assertEqual(len(engine.release_calls), 1)
