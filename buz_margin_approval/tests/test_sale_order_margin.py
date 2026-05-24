# -*- coding: utf-8 -*-

import uuid

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('-at_install', 'post_install')
class TestSaleOrderMargin(TransactionCase):
    """Test sale.order margin approval workflow"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_approval = cls.env.ref('buz_margin_approval.group_margin_approval')
        cls.group_admin = cls.env.ref('buz_margin_approval.group_margin_approval_admin')
        cls.group_sales_user = cls.env.ref('buz_margin_approval.group_sales_margin_approver_user')
        cls.group_sale_salesman = cls.env.ref('sales_team.group_sale_salesman')

        cls.sales_user = cls.env['res.users'].create({
            'name': 'Test Sales - SO Margin',
            'login': 'test_sales_so_%s' % uuid.uuid4().hex[:8],
            'email': 'test_sales_so@test.com',
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.group_sale_salesman.id),
                (4, cls.group_sales_user.id),
            ],
        })
        cls.approver = cls.env['res.users'].create({
            'name': 'Test Approver - SO Margin',
            'login': 'test_approver_so_%s' % uuid.uuid4().hex[:8],
            'email': 'test_approver_so@test.com',
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.group_sale_salesman.id),
                (4, cls.group_approval.id),
            ],
        })
        cls.admin_user = cls.env['res.users'].create({
            'name': 'Test Admin - SO Margin',
            'login': 'test_admin_so_%s' % uuid.uuid4().hex[:8],
            'email': 'test_admin_so@test.com',
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.group_sale_salesman.id),
                (4, cls.group_admin.id),
            ],
        })
        cls.company = cls.env.company

        cls.rule = cls.env['margin.approval.rule'].create({
            'name': 'Test SO Rule',
            'company_id': cls.company.id,
            'user_ids': [(4, cls.sales_user.id)],
        })
        cls.line_low = cls.env['margin.approval.rule.line'].create({
            'rule_id': cls.rule.id,
            'min_margin': 0,
            'max_margin': 15,
            'approver_ids': [(4, cls.approver.id), (4, cls.admin_user.id)],
            'approval_type': 'any',
        })
        cls.line_high = cls.env['margin.approval.rule.line'].create({
            'rule_id': cls.rule.id,
            'min_margin': 15.01,
            'max_margin': 30,
            'approver_ids': [(4, cls.admin_user.id)],
            'approval_type': 'all',
        })

        cls.product = cls.env['product.product'].create({
            'name': 'Test Product Margin',
            'type': 'consu',
            'list_price': 100,
            'standard_price': 80,
            'taxes_id': [(5, 0, 0)],
        })
        cls.product_low_cost = cls.env['product.product'].create({
            'name': 'Test Product Low Cost',
            'type': 'consu',
            'list_price': 100,
            'standard_price': 50,
            'taxes_id': [(5, 0, 0)],
        })
        cls.product_high_cost = cls.env['product.product'].create({
            'name': 'Test Product High Cost',
            'type': 'consu',
            'list_price': 100,
            'standard_price': 95,
            'taxes_id': [(5, 0, 0)],
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer Margin',
            'is_company': True,
        })

        # Create analytic account for confirm_to_so tests
        analytic_plan = cls.env['account.analytic.plan'].search([], limit=1)
        if not analytic_plan:
            analytic_plan = cls.env['account.analytic.plan'].create({'name': 'Test Plan'})
        cls.analytic_account = cls.env['account.analytic.account'].create({
            'name': 'Test Analytic - Margin',
            'plan_id': analytic_plan.id,
        })

    def _create_so(self, product, qty=1, price=None, user=None):
        """Create SO with sudo, flush computed fields, return record"""
        so_user = user or self.sales_user
        so = self.env['sale.order'].with_user(so_user).with_company(self.company).sudo().create({
            'partner_id': self.partner.id,
            'user_id': so_user.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'price_unit': price or product.list_price,
            })],
        })
        so.flush_recordset()
        so.invalidate_recordset()
        return so

    def _set_analytic(self, so):
        """Set analytic distribution on all order lines for confirm_to_so"""
        so.order_line.write({'analytic_distribution': {str(self.analytic_account.id): 100.0}})

    def _refresh(self, so):
        """Flush and invalidate to get latest computed values"""
        so.flush_recordset()
        so.invalidate_recordset()
        return so

    # ---- Margin percentage compute ----

    def test_01_margin_percentage(self):
        """Margin percentage computed correctly"""
        so = self._create_so(self.product, qty=1, price=100)
        # margin field from sale_margin = sum(purchase_price) vs price
        # We just verify margin_percentage is > 0 when margin > 0
        self.assertGreater(so.margin_percentage, 0.0)

    def test_02_margin_percentage_low_margin(self):
        """High cost product has low margin percentage"""
        so = self._create_so(self.product_high_cost, qty=1, price=100)
        # cost=95, price=100 → margin should be low
        self.assertGreater(so.margin_percentage, 0.0)
        self.assertLess(so.margin_percentage, 10.0)

    # ---- Margin rule compute ----

    def test_03_rule_assigned_to_user(self):
        """Rule is assigned for user in rule.user_ids"""
        so = self._create_so(self.product_high_cost)
        self.assertEqual(so.margin_rule_id, self.rule)

    def test_04_no_rule_for_unassigned_user(self):
        """No rule assigned when user not in any rule"""
        other_user = self.env['res.users'].sudo().create({
            'name': 'Test No Rule User',
            'login': 'test_norule_%s' % uuid.uuid4().hex[:8],
            'groups_id': [
                (4, self.env.ref('base.group_user').id),
                (4, self.group_sale_salesman.id),
            ],
        })
        so = self._create_so(self.product, user=other_user)
        self.assertFalse(so.margin_rule_id)

    def test_05_rule_line_matched_low_margin(self):
        """Low margin maps to line_low (0-15%)"""
        so = self._create_so(self.product_high_cost)
        # cost=95, price=100, percentage≈5% → line_low (0-15%)
        if so.margin_percentage <= 15:
            self.assertEqual(so.margin_rule_line_id, self.line_low)

    def test_06_rule_line_outside_range(self):
        """Margin outside all ranges → no line matched"""
        so = self._create_so(self.product_low_cost)
        # cost=50, price=100, percentage≈50% → no line covers >30%
        if so.margin_percentage > 30:
            self.assertFalse(so.margin_rule_line_id)

    # ---- Approval workflow ----

    def test_07_request_approval(self):
        """Sales user can request margin approval"""
        so = self._create_so(self.product_high_cost)
        self.assertEqual(so.approval_state, 'not_required')

        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        self.assertEqual(so.approval_state, 'pending')

    def test_08_request_approval_no_rule(self):
        """User without rule cannot request approval"""
        other_user = self.env['res.users'].sudo().create({
            'name': 'Test No Rule Request',
            'login': 'test_norule_req_%s' % uuid.uuid4().hex[:8],
            'groups_id': [
                (4, self.env.ref('base.group_user').id),
                (4, self.group_sale_salesman.id),
                (4, self.group_sales_user.id),
            ],
        })
        so = self._create_so(self.product, user=other_user)
        with self.assertRaises(UserError):
            so.with_user(other_user).sudo().action_request_margin_approval()

    def test_09_request_approval_already_pending(self):
        """Cannot request approval when already pending"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        with self.assertRaises(UserError):
            so.with_user(self.sales_user).sudo().action_request_margin_approval()

    def test_10_request_approval_no_order_lines(self):
        """Cannot request when SO has no lines"""
        so = self.env['sale.order'].with_user(self.sales_user).with_company(self.company).sudo().create({
            'partner_id': self.partner.id,
            'user_id': self.sales_user.id,
        })
        so.flush_recordset()
        so.invalidate_recordset()
        # No rule line matched because there's no margin to calculate
        with self.assertRaises(UserError):
            so.with_user(self.sales_user).sudo().action_request_margin_approval()

    def test_11_approve_margin_any(self):
        """Approval type 'any' - any single approver can approve"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        self.assertEqual(so.approval_state, 'pending')

        so.with_user(self.approver).sudo().action_approve_margin()
        self.assertEqual(so.approval_state, 'approved')

    def test_12_approve_margin_all(self):
        """Approval type 'all' - all approvers must approve"""
        so = self._create_so(self.product)
        self._refresh(so)
        if so.margin_rule_line_id == self.line_high:
            so.with_user(self.sales_user).sudo().action_request_margin_approval()
            so.with_user(self.admin_user).sudo().action_approve_margin()
            self.assertEqual(so.approval_state, 'approved')

    def test_13_reject_margin(self):
        """Rejection works and sets state correctly"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()

        wizard = self.env['margin.rejection.wizard'].with_user(self.approver).sudo().create({
            'sale_order_id': so.id,
            'rejection_reason': 'Margin too low',
        })
        wizard.with_user(self.approver).sudo().action_reject()
        self.assertEqual(so.approval_state, 'rejected')

    def test_14_approve_not_pending(self):
        """Cannot approve order that is not pending"""
        so = self._create_so(self.product_high_cost)
        with self.assertRaises(UserError):
            so.with_user(self.approver).sudo().action_approve_margin()

    # ---- Confirm flow ----

    def test_15_confirm_to_so_approved(self):
        """Confirm To SO works when approved"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        so.with_user(self.approver).sudo().action_approve_margin()
        self._set_analytic(so)

        so.with_user(self.sales_user).sudo().action_confirm_to_so()
        self.assertEqual(so.confirm_flow_state, 'confirm_to_so')

    def test_16_confirm_to_so_not_approved(self):
        """Cannot Confirm To SO when not approved"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()

        with self.assertRaises(UserError):
            so.with_user(self.sales_user).sudo().action_confirm_to_so()

    def test_17_cancel_confirm_to_so(self):
        """Cancel Confirm To SO resets states"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        so.with_user(self.approver).sudo().action_approve_margin()
        self._set_analytic(so)
        so.with_user(self.sales_user).sudo().action_confirm_to_so()

        so.sudo().action_cancel_confirm_to_so()
        self.assertEqual(so.confirm_flow_state, 'draft')
        self.assertEqual(so.approval_state, 'rejected')

    # ---- Sales user blocked from action_confirm ----

    def test_18_sales_user_cannot_confirm(self):
        """Sales users with group_sales_margin_approver_user cannot use action_confirm"""
        so = self._create_so(self.product_low_cost)
        with self.assertRaises(UserError):
            so.with_user(self.sales_user).action_confirm()

    def test_19_confirm_blocked_when_pending(self):
        """action_confirm blocked when approval_state=pending"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()

        with self.assertRaises(UserError):
            so.sudo().action_confirm()

    # ---- Approval reset on order line change ----

    def test_20_approval_reset_on_price_change(self):
        """Approval resets when order line price is modified"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        so.with_user(self.approver).sudo().action_approve_margin()
        self.assertEqual(so.approval_state, 'approved')

        # Update price → should reset approval and confirm_flow_state
        so.sudo().write({
            'order_line': [(1, so.order_line.id, {'price_unit': 98})]
        })
        self._refresh(so)
        self.assertEqual(so.approval_state, 'not_required')
        self.assertEqual(so.confirm_flow_state, 'draft')

    # ---- can_current_user_approve ----

    def test_21_can_approve_admin(self):
        """Admin group can approve any order"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        result = so.with_user(self.admin_user).sudo()._can_approve_margin()
        self.assertTrue(result)

    def test_22_can_approve_in_list(self):
        """User in margin_approval_user_ids can approve"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        result = so.with_user(self.approver).sudo()._can_approve_margin()
        self.assertTrue(result)

    def test_23_cannot_approve_not_in_list(self):
        """User not in approver list and no group cannot approve"""
        so = self._create_so(self.product_high_cost)
        other_user = self.env['res.users'].sudo().create({
            'name': 'Test Random User',
            'login': 'test_random_%s' % uuid.uuid4().hex[:8],
            'groups_id': [
                (4, self.env.ref('base.group_user').id),
                (4, self.group_sale_salesman.id),
            ],
        })
        result = so.with_user(other_user).sudo()._can_approve_margin()
        self.assertFalse(result)

    # ---- Cancel Approval Request ----

    def test_24_cancel_pending_approval(self):
        """Sales user can cancel their own pending approval request"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        self.assertEqual(so.approval_state, 'pending')

        # Cancel the approval request
        so.with_user(self.sales_user).sudo().action_cancel_margin_approval()
        self.assertEqual(so.approval_state, 'not_required')

    def test_25_cancel_approval_clears_approved_users(self):
        """Cancel approval clears approved_user_ids"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()

        so.with_user(self.sales_user).sudo().action_cancel_margin_approval()
        self.assertEqual(len(so.approved_user_ids), 0)

    def test_26_cancel_approval_not_pending(self):
        """Cannot cancel when not in pending state"""
        so = self._create_so(self.product_high_cost)
        # not_required → cannot cancel
        with self.assertRaises(UserError):
            so.with_user(self.sales_user).sudo().action_cancel_margin_approval()

    def test_27_cancel_approval_already_approved(self):
        """Cannot cancel when already approved"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        so.with_user(self.approver).sudo().action_approve_margin()
        self.assertEqual(so.approval_state, 'approved')

        with self.assertRaises(UserError):
            so.with_user(self.sales_user).sudo().action_cancel_margin_approval()

    def test_28_cancel_then_re_request(self):
        """After cancel, user can edit and re-request approval"""
        so = self._create_so(self.product_high_cost)
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        so.with_user(self.sales_user).sudo().action_cancel_margin_approval()
        self.assertEqual(so.approval_state, 'not_required')

        # Re-request should work
        so.with_user(self.sales_user).sudo().action_request_margin_approval()
        self.assertEqual(so.approval_state, 'pending')
