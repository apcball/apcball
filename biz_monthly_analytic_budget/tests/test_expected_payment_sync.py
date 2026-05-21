# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from .common import BudgetTestMixin


class TestExpectedPaymentSync(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()

    def test_pr_payment_date_change_syncs_to_po(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target)
        pr = self._create_pr(target=target)
        po = self._create_po(target=target, pr_name=pr.name)

        new_date = target + timedelta(days=5)
        pr.write({'payment_date': new_date, 'payment_date_manual': new_date})
        self.assertEqual(po.payment_date, new_date)

    def test_po_payment_date_change_syncs_back_to_pr(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target)
        pr = self._create_pr(target=target, state='waiting_purchase_approval')
        po = self._create_po(target=target, pr_name=pr.name)

        new_date = target + timedelta(days=7)
        po.write({'payment_date': new_date, 'payment_date_manual': new_date})
        self.assertEqual(pr.payment_date, new_date)

    def test_no_infinite_loop_on_sync(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target)
        pr = self._create_pr(target=target)
        po = self._create_po(target=target, pr_name=pr.name)

        new_date = target + timedelta(days=10)
        pr.write({'payment_date': new_date, 'payment_date_manual': new_date})
        self.assertEqual(po.payment_date, new_date)
        self.assertEqual(pr.payment_date, new_date)
