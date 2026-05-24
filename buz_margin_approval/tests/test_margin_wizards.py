# -*- coding: utf-8 -*-

import uuid

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('-at_install', 'post_install')
class TestMarginWizards(TransactionCase):
    """Test margin approval and rejection wizards"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_approval = cls.env.ref('buz_margin_approval.group_margin_approval')
        cls.group_sales_user = cls.env.ref('buz_margin_approval.group_sales_margin_approver_user')

        cls.sales_user = cls.env['res.users'].create({
            'name': 'Test Sales - Wizard',
            'login': 'test_sales_wiz_%s' % uuid.uuid4().hex[:8],
            'email': 'test_sales_wiz@test.com',
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('sales_team.group_sale_salesman').id),
                (4, cls.group_sales_user.id),
            ],
        })
        cls.approver = cls.env['res.users'].create({
            'name': 'Test Approver - Wizard',
            'login': 'test_approver_wiz_%s' % uuid.uuid4().hex[:8],
            'email': 'test_approver_wiz@test.com',
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('sales_team.group_sale_salesman').id),
                (4, cls.group_approval.id),
            ],
        })
        cls.company = cls.env.company

        cls.rule = cls.env['margin.approval.rule'].create({
            'name': 'Test Wizard Rule',
            'company_id': cls.company.id,
            'user_ids': [(4, cls.sales_user.id)],
        })
        cls.env['margin.approval.rule.line'].create({
            'rule_id': cls.rule.id,
            'min_margin': 0,
            'max_margin': 20,
            'approver_ids': [(4, cls.approver.id)],
            'approval_type': 'any',
        })

        cls.product = cls.env['product.product'].create({
            'name': 'Test Product Wizard',
            'type': 'consu',
            'list_price': 100,
            'standard_price': 90,
            'taxes_id': [(5, 0, 0)],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer Wizard',
        })

    def _create_so(self):
        so = self.env['sale.order'].with_user(self.sales_user).with_company(self.company).sudo().create({
            'partner_id': self.partner.id,
            'user_id': self.sales_user.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': 100,
            })],
        })
        so.flush_recordset()
        so.invalidate_recordset()
        return so

    def _set_analytic(self, so):
        """Set analytic distribution on all order lines for confirm_to_so"""
        analytic_plan = self.env['account.analytic.plan'].search([], limit=1)
        if not analytic_plan:
            analytic_plan = self.env['account.analytic.plan'].create({'name': 'Test Plan'})
        analytic_account = self.env['account.analytic.account'].create({
            'name': 'Test Analytic - Wizard',
            'plan_id': analytic_plan.id,
        })
        so.order_line.write({'analytic_distribution': {str(analytic_account.id): 100.0}})

    # ---- Approval Wizard ----

    def test_01_approval_wizard_send(self):
        """Approval wizard sets state to pending and posts message"""
        so = self._create_so()

        wizard = self.env['margin.approval.wizard'].create({
            'sale_order_id': so.id,
            'note': 'Please approve this urgent order',
        })
        wizard.action_send()

        self.assertEqual(so.approval_state, 'pending')

    # ---- Rejection Wizard ----

    def test_02_rejection_wizard_reject(self):
        """Rejection wizard sets state to rejected with reason"""
        so = self._create_so()
        so.with_user(self.sales_user).sudo().action_request_margin_approval()

        wizard = self.env['margin.rejection.wizard'].with_user(self.approver).sudo().create({
            'sale_order_id': so.id,
            'rejection_reason': 'Margin below threshold',
        })
        wizard.with_user(self.approver).sudo().action_reject()

        self.assertEqual(so.approval_state, 'rejected')

    def test_03_rejection_wizard_no_reason(self):
        """Rejection wizard requires a reason"""
        so = self._create_so()
        so.with_user(self.sales_user).sudo().action_request_margin_approval()

        wizard = self.env['margin.rejection.wizard'].with_user(self.approver).sudo().create({
            'sale_order_id': so.id,
            'rejection_reason': '',
        })
        with self.assertRaises(UserError):
            wizard.with_user(self.approver).sudo().action_reject()

    def test_04_rejection_wizard_unauthorized(self):
        """Unauthorized user cannot reject"""
        so = self._create_so()
        so.action_request_margin_approval()

        other_user = self.env['res.users'].sudo().create({
            'name': 'Test Unauthorized - Wizard',
            'login': 'test_unauth_wiz_%s' % uuid.uuid4().hex[:8],
            'groups_id': [(4, self.env.ref('base.group_user').id)],
        })

        wizard = self.env['margin.rejection.wizard'].with_user(other_user).sudo().create({
            'sale_order_id': so.id,
            'rejection_reason': 'Not my job',
        })
        with self.assertRaises(UserError):
            wizard.with_user(other_user).sudo().action_reject()

    # ---- Full workflow via wizards ----

    def test_05_full_workflow_wizards(self):
        """Complete flow: request → approve → confirm_to_so"""
        so = self._create_so()

        # Request via wizard
        wizard = self.env['margin.approval.wizard'].sudo().create({
            'sale_order_id': so.id,
        })
        wizard.action_send()
        self.assertEqual(so.approval_state, 'pending')

        # Approve
        so.with_user(self.approver).sudo().action_approve_margin()
        self.assertEqual(so.approval_state, 'approved')

        # Set analytic before confirm_to_so
        self._set_analytic(so)

        # Confirm To SO
        so.with_user(self.sales_user).sudo().action_confirm_to_so()
        self.assertEqual(so.confirm_flow_state, 'confirm_to_so')
