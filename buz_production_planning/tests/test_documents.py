# pylint: disable=protected-access  # tests exercise internal entry points
from datetime import timedelta
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged

from odoo.addons.buz_production_planning.engine.mrp_netting import solve

from .common import MONDAY, BlanketCommon, PlanCommon


@tagged('post_install', '-at_install')
class TestCreateDocuments(PlanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.picking_type = cls.env['stock.picking.type'].search(
            [('code', '=', 'mrp_operation'), ('company_id', '=', cls.env.company.id)], limit=1)
        # buz_partner_required_fields (installed on DEV/prod) demands a full contact.
        thailand = cls.env.ref('base.th')
        cls.contact = contact = {
            'street': '1 Test Rd', 'street2': 'Test Sub-district', 'city': 'Bangkok',
            'state_id': cls.env['res.country.state'].search([('country_id', '=', thailand.id)], limit=1).id,
            'zip': '10110', 'country_id': thailand.id, 'phone': '021234567',
            'email': 'test-vendor@example.com',
        }
        cls.vendor_a = cls.env['res.partner'].create({'name': 'TEST Vendor A', **contact})
        cls.vendor_b = cls.env['res.partner'].create({'name': 'TEST Vendor B', **contact})
        cls.bom = cls._bom(cls.fg, [(cls.rm, 2)])
        cls.run_ = cls.env['buz.plan.run'].create({
            'date_from': MONDAY, 'horizon_weeks': 4, 'state': 'computed'})

    def _sugg(self, product, action='make', qty=5.0, **kw):
        vals = {
            'run_id': self.run_.id, 'product_id': product.id, 'action': action, 'qty': qty,
            'uom_id': product.uom_id.id, 'date_need': MONDAY + timedelta(days=7),
            'date_release': MONDAY + timedelta(days=4), 'state': 'approved',
        }
        if action == 'make':
            vals.update(bom_id=self.bom.id, picking_type_id=self.picking_type.id)
        vals.update(kw)
        return self.env['buz.plan.suggestion'].create(vals)

    def _wizard(self, suggestions, buy_document='bo'):
        return self.env['buz.plan.create.documents.wizard'].create({
            'run_id': self.run_.id, 'buy_document': buy_document,
            'suggestion_ids': [Command.set(suggestions.ids)]})

    def test_make_creates_draft_mo_not_confirmed(self):
        s = self._sugg(self.fg, qty=7)
        result = self._wizard(s)._create_documents()
        mo = result['productions']
        self.assertEqual(len(mo), 1)
        self.assertEqual(mo.state, 'draft', "never confirmed")
        self.assertEqual(mo.origin, self.run_.name)
        self.assertEqual(mo.product_qty, 7)
        self.assertEqual(mo.bom_id, self.bom)
        self.assertEqual(mo.picking_type_id, self.picking_type)
        self.assertTrue(mo.date_deadline, "deadline filled from date_need")
        self.assertGreater(mo.date_deadline, mo.date_start)
        self.assertEqual(s.production_id, mo)
        self.assertEqual(s.state, 'done')
        self.assertFalse(mo.move_raw_ids.filtered(lambda m: m.state not in ('draft',)), "no reservation")

    def test_mo_creation_touches_no_stock(self):
        quants_before = self.env['stock.quant'].search_count([('product_id', 'in', (self.fg | self.rm).ids)])
        self._wizard(self._sugg(self.fg))._create_documents()
        self.assertEqual(
            self.env['stock.quant'].search_count([('product_id', 'in', (self.fg | self.rm).ids)]),
            quants_before)
        self.assertFalse(self.env['stock.move.line'].search_count([('product_id', 'in', (self.fg | self.rm).ids)]))

    def test_make_without_picking_type_blocks_and_names_product(self):
        s = self._sugg(self.fg, picking_type_id=False)
        with self.assertRaises(UserError) as cm:
            self._wizard(s)._create_documents()
        self.assertIn('TEST-FG', str(cm.exception))
        self.assertIn('Product Parameters', str(cm.exception))
        self.assertFalse(s.production_id)

    def test_buy_groups_by_vendor(self):
        s1 = self._sugg(self.rm, 'buy', 10, vendor_id=self.vendor_a.id)
        s2 = self._sugg(self.semi, 'buy', 4, vendor_id=self.vendor_a.id)
        s3 = self._sugg(self.fg, 'buy', 3, vendor_id=self.vendor_b.id)
        result = self._wizard(s1 | s2 | s3, 'rfq')._create_documents()
        orders = result['orders']
        self.assertEqual(len(orders), 2)
        order_a = orders.filtered(lambda o: o.partner_id == self.vendor_a)
        self.assertEqual(len(order_a.order_line), 2)
        self.assertEqual(order_a.state, 'draft')
        self.assertEqual(order_a.origin, self.run_.name)
        self.assertEqual(s1.purchase_line_id.order_id, order_a)
        self.assertEqual(s1.purchase_line_id.product_qty, 10)
        self.assertEqual(s3.purchase_line_id.order_id.partner_id, self.vendor_b)
        self.assertEqual({s1.state, s2.state, s3.state}, {'done'})

    def test_buy_without_vendor_skipped_and_reported(self):
        ok = self._sugg(self.rm, 'buy', 10, vendor_id=self.vendor_a.id)
        bad = self._sugg(self.semi, 'buy', 4)
        result = self._wizard(ok | bad, 'rfq')._create_documents()
        self.assertEqual(len(result['orders']), 1)
        self.assertEqual(result['no_vendor'], bad)
        self.assertEqual(bad.state, 'approved', "stays actionable")
        self.assertFalse(bad.purchase_line_id)
        self.assertIn('TEST-SEMI', self.run_.message_ids[0].body)

    def test_rerun_does_not_duplicate(self):
        s = self._sugg(self.fg)
        self._wizard(s)._create_documents()
        mos = self.env['mrp.production'].search_count([('origin', '=', self.run_.name)])
        result = self._wizard(s)._create_documents()
        self.assertFalse(result['productions'])
        self.assertEqual(result['existing'], s)
        self.assertEqual(self.env['mrp.production'].search_count([('origin', '=', self.run_.name)]), mos)

    def test_proposed_is_approved_in_wizard(self):
        s = self._sugg(self.fg, state='proposed')
        self._wizard(s)._create_documents()
        self.assertEqual(s.state, 'done')

    def test_rejected_is_not_created(self):
        s = self._sugg(self.fg, state='rejected')
        result = self._wizard(s)._create_documents()
        self.assertFalse(result['productions'])
        self.assertEqual(s.state, 'rejected')

    def test_rejected_without_line_or_vendor_does_not_block(self):
        """A rejected suggestion is ignored even when it could not be created."""
        rejected = self._sugg(self.semi, state='rejected', picking_type_id=False)
        rejected_buy = self._sugg(self.rm, 'buy', 3, state='rejected')
        good = self._sugg(self.fg)
        wizard = self._wizard(rejected | rejected_buy | good)
        self.assertNotIn('TEST-SEMI', wizard.summary)
        self.assertNotIn('TEST-RM', wizard.summary)
        result = wizard._create_documents()
        self.assertEqual(len(result['productions']), 1)
        self.assertFalse(result['no_vendor'])
        self.assertEqual((rejected | rejected_buy).mapped('state'), ['rejected', 'rejected'])

    def test_mo_takes_analytic_of_latest_mo_and_reports_refusals(self):
        """Prod makes BU + Production analytic mandatory on every MO."""
        plan = self.env['account.analytic.plan'].create({'name': 'TEST Production'})
        account = self.env['account.analytic.account'].create({'name': 'TEST Line A', 'plan_id': plan.id})
        dist = {str(account.id): 100.0}
        self.env['mrp.production'].create({
            'product_id': self.fg.id, 'product_qty': 1, 'bom_id': self.bom.id,
            'picking_type_id': self.picking_type.id, 'analytic_distribution': dist})
        self.env['account.analytic.applicability'].create({
            'analytic_plan_id': plan.id, 'business_domain': 'manufacturing_order',
            'applicability': 'mandatory'})
        semi_bom = self._bom(self.semi, [(self.rm, 1)])
        known = self._sugg(self.fg, qty=3)
        unknown = self._sugg(self.semi, qty=2, bom_id=semi_bom.id)
        result = self._wizard(known | unknown)._create_documents()
        mo = result['productions']
        self.assertEqual(len(mo), 1, "the MO with history is still created")
        self.assertEqual(mo.analytic_distribution, dist)
        self.assertEqual([s for s, _msg in result['blocked']], [unknown])
        self.assertEqual(unknown.state, 'approved', "stays actionable once the planner fixes it")
        self.assertIn('TEST-SEMI', self.run_.message_ids[0].body)

    def test_run_state_follows_remaining_suggestions(self):
        a = self._sugg(self.fg)
        b = self._sugg(self.rm, 'buy', 1, vendor_id=self.vendor_a.id)
        self._wizard(a)._create_documents()
        self.assertEqual(self.run_.state, 'confirmed')
        self._wizard(b, 'rfq')._create_documents()
        self.assertEqual(self.run_.state, 'done')

    def test_draft_plan_cannot_create(self):
        self.run_.state = 'draft'
        with self.assertRaises(UserError):
            self._wizard(self._sugg(self.fg))._create_documents()

    def test_planner_without_admin_rights_can_create(self):
        """Plain Planning / User (no sudo anywhere) must be able to create the drafts."""
        user = self.env['res.users'].create({
            'name': 'TEST planner', 'login': 'test_planner_x', **self.contact,
            'groups_id': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('buz_production_planning.group_plan_user').id])],
        })
        s = self._sugg(self.fg)
        b = self._sugg(self.rm, 'buy', 2, vendor_id=self.vendor_a.id)
        wiz = self.env['buz.plan.create.documents.wizard'].with_user(user).create({
            'run_id': self.run_.id, 'buy_document': 'rfq',
            'suggestion_ids': [Command.set((s | b).ids)]})
        result = wiz._create_documents()
        self.assertEqual((len(result['productions']), len(result['orders'])), (1, 1))

    def test_smart_button_on_mo(self):
        s = self._sugg(self.fg)
        mo = self._wizard(s)._create_documents()['productions']
        self.assertEqual(mo.buz_plan_run_id, self.run_)
        self.assertEqual(mo.action_open_buz_plan()['res_id'], self.run_.id)


@tagged('post_install', '-at_install')
class TestBlanketOrders(BlanketCommon):
    """Buy suggestions become draft blanket orders (purchase.requisition)."""

    # -- creation ---------------------------------------------------------
    def test_two_vendors_two_blanket_orders(self):
        s1 = self._sugg(self.p1, 10, self.vendor_a, day=7)
        s2 = self._sugg(self.p2, 4, self.vendor_a, day=14)
        s3 = self._sugg(self.p3, 3, self.vendor_b, day=7)
        result = self._wizard(s1 | s2 | s3)._create_documents()
        bos = result['requisitions']
        self.assertEqual(len(bos), 2)
        self.assertFalse(result['orders'], "no RFQ in Blanket Order mode")
        bo_a = bos.filtered(lambda r: r.vendor_id == self.vendor_a)
        self.assertEqual(bo_a.state, 'draft')
        self.assertEqual(bo_a.type_id.quantity_copy, 'none')
        self.assertEqual(bo_a.origin, self.run_.name)
        self.assertEqual(bo_a.buz_plan_run_id, self.run_)
        self.assertEqual(bo_a.user_id, self.env.user)
        self.assertEqual(bo_a.schedule_date, MONDAY + timedelta(days=7), "earliest date_need")
        self.assertTrue(bo_a.date_end)
        self.assertEqual(len(bo_a.line_ids), 2)
        line1 = s1.requisition_line_id
        self.assertEqual((line1.product_id, line1.product_qty), (self.p1, 10))
        self.assertEqual(line1.schedule_date, MONDAY + timedelta(days=7))
        self.assertEqual(s2.requisition_line_id.schedule_date, MONDAY + timedelta(days=14))
        self.assertEqual(s3.requisition_id.vendor_id, self.vendor_b)
        self.assertEqual({s1.state, s2.state, s3.state}, {'done'})
        self.assertEqual(self.run_.state, 'done')

    def test_quantity_converted_to_purchase_unit(self):
        dozen = self.env.ref('uom.product_uom_dozen')
        self.p1.uom_po_id = dozen
        s = self._sugg(self.p1, 24)
        self._wizard(s)._create_documents()
        self.assertEqual(s.requisition_line_id.product_uom_id, dozen)
        self.assertEqual(s.requisition_line_id.product_qty, 2)

    def test_nothing_confirmed_no_stock_no_po_no_supplierinfo(self):
        s = self._sugg(self.p1, 10)
        self._wizard(s)._create_documents()
        bo = s.requisition_id
        self.assertEqual(bo.state, 'draft')
        self.assertEqual(bo.name, 'New', "number is assigned on confirmation by purchasing")
        self.assertFalse(bo.purchase_ids)
        self.assertFalse(self.env['purchase.order'].search_count([('origin', 'ilike', self.run_.name)]))
        self.assertFalse(self.env['stock.move'].search_count([('product_id', '=', self.p1.id)]))
        self.assertFalse(self.env['product.supplierinfo'].search_count(
            [('purchase_requisition_line_id', 'in', bo.line_ids.ids)]))

    def test_price_fallback_order(self):
        # p1: vendor pricelist wins over an older blanket order line
        self.p1.product_tmpl_id.seller_ids = [Command.create(
            {'partner_id': self.vendor_a.id, 'price': 5.0, 'min_qty': 0})]
        self._hand_bo(self.vendor_a, self.p1, price=7.0)
        # p2: latest blanket order line of this vendor
        self._hand_bo(self.vendor_a, self.p2, price=8.0)
        # p3: latest confirmed PO line of this vendor
        self._po(self.vendor_a, self.p3, price=9.0)
        sugg = self._sugg(self.p1) | self._sugg(self.p2) | self._sugg(self.p3) | self._sugg(self.p4)
        result = self._wizard(sugg)._create_documents()
        prices = {s.product_id: s.requisition_line_id.price_unit for s in sugg}
        self.assertEqual(prices, {self.p1: 5.0, self.p2: 8.0, self.p3: 9.0, self.p4: 0.0})
        self.assertEqual(result['no_price'].product_id, self.p4, "0 is reported, not hidden")
        self.assertIn('TEST-BO4', self.run_.message_ids[0].body)

    def test_zero_price_blanket_line_is_not_a_price_source(self):
        self._hand_bo(self.vendor_a, self.p1, price=0.0)
        s = self._sugg(self.p1)
        self._wizard(s)._create_documents()
        self.assertEqual(s.requisition_line_id.price_unit, 0.0)

    def test_analytic_from_latest_line_and_missing_reported(self):
        self._hand_bo(self.vendor_a, self.p1, price=1.0, line={'analytic_distribution': self.dist})
        po_line_product = self.p2
        po = self._po(self.vendor_a, po_line_product, price=2.0)
        po.order_line.analytic_distribution = self.dist
        s1, s2, s3 = self._sugg(self.p1), self._sugg(po_line_product), self._sugg(self.p3)
        result = self._wizard(s1 | s2 | s3)._create_documents()
        self.assertEqual(s1.requisition_line_id.analytic_distribution, self.dist, "from blanket order")
        self.assertEqual(s2.requisition_line_id.analytic_distribution, self.dist, "from PO line")
        self.assertFalse(s3.requisition_line_id.analytic_distribution)
        self.assertEqual(result['no_analytic'], s3, "reported, not an error")
        self.assertEqual(s3.state, 'done')

    def test_currency_and_picking_type_from_latest_blanket_order(self):
        usd = self.env.ref('base.USD')
        picking = self.warehouse.in_type_id
        self._hand_bo(self.vendor_a, self.p1, price=1.0, currency_id=usd.id, picking_type_id=picking.id)
        s = self._sugg(self.p2)
        self._wizard(s)._create_documents()
        bo = s.requisition_id
        self.assertEqual(bo.currency_id, usd)
        self.assertEqual(bo.picking_type_id, picking)

    def test_receipt_type_outside_plan_warehouses_is_not_used(self):
        """A receipt into a warehouse the plan does not count would never be netted."""
        outside = self.other_wh.in_type_id
        self._hand_bo(self.vendor_a, self.p1, price=1.0, picking_type_id=outside.id)
        s = self._sugg(self.p2)
        self._wizard(s)._create_documents()
        self.assertEqual(s.requisition_id.picking_type_id, self.warehouse.in_type_id)

    def test_vendor_without_history_uses_vendor_currency_and_plan_warehouse(self):
        s = self._sugg(self.p1, vendor=self.vendor_b)
        self._wizard(s)._create_documents()
        bo = s.requisition_id
        expected = (self.vendor_b.with_company(self.company).property_purchase_currency_id
                    or self.company.currency_id)
        self.assertEqual(bo.currency_id, expected)
        self.assertEqual(bo.picking_type_id, self.warehouse.in_type_id)

    def test_no_blanket_order_type_raises_clear_error(self):
        s = self._sugg(self.p1)
        self.env['purchase.requisition.type'].search([('quantity_copy', '=', 'none')]).write(
            {'quantity_copy': 'copy'})
        with self.assertRaises(UserError) as cm:
            self._wizard(s)._create_documents()
        self.assertIn('Set quantities manually', str(cm.exception))

    # -- skipping / safety ----------------------------------------------------
    def test_no_vendor_skipped_and_reported(self):
        ok = self._sugg(self.p1)
        bad = self._sugg(self.p2, vendor=self.vendor_a)
        bad.vendor_id = False
        result = self._wizard(ok | bad)._create_documents()
        self.assertEqual(len(result['requisitions']), 1)
        self.assertEqual(result['no_vendor'], bad)
        self.assertEqual(bad.state, 'approved')
        self.assertFalse(bad.requisition_line_id)
        self.assertIn('TEST-BO2', self.run_.message_ids[0].body)

    def test_rerun_does_not_duplicate(self):
        s = self._sugg(self.p1)
        self._wizard(s)._create_documents()
        count = self.env['purchase.requisition'].search_count([('buz_plan_run_id', '=', self.run_.id)])
        result = self._wizard(s)._create_documents()
        self.assertFalse(result['requisitions'])
        self.assertEqual(result['existing'], s)
        self.assertEqual(
            self.env['purchase.requisition'].search_count([('buz_plan_run_id', '=', self.run_.id)]), count)

    def test_default_get_leaves_out_suggestions_with_a_blanket_order(self):
        done = self._sugg(self.p1)
        todo = self._sugg(self.p2)
        self._wizard(done)._create_documents()
        defaults = self.env['buz.plan.create.documents.wizard'].with_context(
            default_run_id=self.run_.id).default_get(['run_id', 'suggestion_ids'])
        ids = set(defaults['suggestion_ids'][0][2])
        self.assertIn(todo.id, ids)
        self.assertNotIn(done.id, ids)

    def test_one_vendor_failing_does_not_stop_the_others(self):
        good = self._sugg(self.p1, vendor=self.vendor_a)
        bad = self._sugg(self.p2, vendor=self.vendor_b)
        Line = type(self.env['purchase.requisition.line'])
        original = Line.create

        def refuse(model, vals_list):
            if any(v.get('product_id') == self.p2.id for v in vals_list):
                raise ValidationError("TEST refused by a validation")
            return original(model, vals_list)

        with patch.object(Line, 'create', refuse):
            result = self._wizard(good | bad)._create_documents()
        self.assertEqual(result['requisitions'].vendor_id, self.vendor_a)
        self.assertEqual([s for s, _msg in result['blocked']], [bad])
        self.assertEqual(bad.state, 'approved', "stays actionable")
        self.assertFalse(bad.requisition_line_id)
        self.assertFalse(self.env['purchase.requisition'].search_count(
            [('vendor_id', '=', self.vendor_b.id), ('buz_plan_run_id', '=', self.run_.id)]),
            "the failed vendor leaves no half-made order")
        self.assertIn('TEST refused', self.run_.message_ids[0].body)

    def test_planner_without_admin_rights_can_create_blanket_order(self):
        user = self.env['res.users'].create({
            'name': 'TEST bo planner', 'login': 'test_bo_planner_x', **self._contact_vals(),
            'groups_id': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('buz_production_planning.group_plan_user').id])],
        })
        self.assertFalse(user.has_group('base.group_system'))
        s = self._sugg(self.p1)
        wiz = self.env['buz.plan.create.documents.wizard'].with_user(user).create({
            'run_id': self.run_.id, 'buy_document': 'bo', 'suggestion_ids': [Command.set(s.ids)]})
        self.assertIn('Blanket orders', wiz.summary)
        result = wiz._create_documents()
        self.assertEqual(len(result['requisitions']), 1)
        self.assertEqual(result['requisitions'].user_id, user)

    def test_rfq_choice_keeps_old_behaviour(self):
        s = self._sugg(self.p1)
        result = self._wizard(s, 'rfq')._create_documents()
        self.assertEqual(len(result['orders']), 1)
        self.assertFalse(result['requisitions'])
        self.assertEqual(s.purchase_line_id.order_id, result['orders'])
        self.assertFalse(s.requisition_line_id)

    # -- links ---------------------------------------------------------------
    def test_links_between_plan_and_documents(self):
        s = self._sugg(self.p1)
        self._wizard(s)._create_documents()
        bo = s.requisition_id
        self.assertTrue(bo)
        self.assertEqual(s.requisition_line_id.requisition_id, bo)
        self.assertEqual(s.document_state, 'draft')
        self.assertIn('Blanket Order (draft)', s.document_ref, "draft BO is named New")
        action = s.action_open_document()
        self.assertEqual((action['res_model'], action['res_id']), ('purchase.requisition', bo.id))
        back = bo.action_open_buz_plan()
        self.assertEqual((back['res_model'], back['res_id']), ('buz.plan.run', self.run_.id))
        bo.state = 'ongoing'
        bo.name = 'BO-TEST0001'
        self.assertEqual(s.document_state, 'open')
        self.assertEqual(s.document_ref, 'BO-TEST0001')
        bo.state = 'done'
        self.assertEqual(s.document_state, 'done')
        bo.state = 'cancel'
        self.assertEqual(s.document_state, 'cancel')

    def test_open_document_without_document_raises(self):
        with self.assertRaises(UserError):
            self._sugg(self.p1).action_open_document()

    def test_po_issued_from_blanket_order_points_to_plan(self):
        s = self._sugg(self.p1, 10)
        self._wizard(s)._create_documents()
        bo = s.requisition_id
        po = self._po(self.vendor_a, self.p1, 1.0, qty=4, state='draft', requisition=bo)
        self.assertEqual(po.buz_plan_run_id, self.run_)
        self.assertEqual(po.action_open_buz_plan()['res_id'], self.run_.id)
        hand_made = self._po(self.vendor_a, self.p1, 1.0, state='draft')
        self.assertFalse(hand_made.buz_plan_run_id)
        self.assertFalse(hand_made.action_open_buz_plan())

    def test_rfq_is_linked_to_plan(self):
        s = self._sugg(self.p1)
        self._wizard(s, 'rfq')._create_documents()
        po = s.purchase_order_id
        self.assertEqual(po.buz_plan_run_id, self.run_)
        self.assertEqual(s.document_state, 'draft')
        self.assertEqual(s.document_ref, po.name)

    def test_plan_counts_and_actions(self):
        mo_product = self._product('BOMO')
        bom = self._bom(mo_product, [(self.p4, 1)])
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'mrp_operation'), ('company_id', '=', self.company.id)], limit=1)
        make = self.env['buz.plan.suggestion'].create({
            'run_id': self.run_.id, 'product_id': mo_product.id, 'action': 'make', 'qty': 2,
            'uom_id': mo_product.uom_id.id, 'date_need': MONDAY + timedelta(days=7),
            'date_release': MONDAY + timedelta(days=4), 'state': 'approved',
            'bom_id': bom.id, 'picking_type_id': picking_type.id})
        rfq = self._sugg(self.p3, vendor=self.vendor_b)
        bo_sugg = self._sugg(self.p1, 10)
        self._wizard(rfq, 'rfq')._create_documents()
        self._wizard(make | bo_sugg)._create_documents()
        po = self._po(self.vendor_a, self.p1, 1.0, qty=4, state='draft', requisition=bo_sugg.requisition_id)
        self._po(self.vendor_a, self.p1, 1.0, state='draft')    # hand-made: not the plan's
        run = self.run_
        run.invalidate_recordset()
        self.assertEqual((run.production_count, run.requisition_count, run.purchase_count), (1, 1, 2))
        self.assertEqual(run.document_count, 3)
        self.assertEqual(run.action_open_productions()['domain'], [('id', 'in', make.production_id.ids)])
        self.assertEqual(run.action_open_requisitions()['domain'], [('buz_plan_run_id', '=', run.id)])
        domain = run.action_open_purchases()['domain']
        self.assertEqual(self.env['purchase.order'].search(domain), po | rfq.purchase_order_id)

    def test_next_step_hint_follows_the_flow(self):
        run = self.env['buz.plan.run'].create({
            'date_from': MONDAY, 'horizon_weeks': 4, 'warehouse_ids': [Command.set(self.warehouse.ids)]})
        self.assertEqual(run.next_step, 'compute')
        self.assertIn('Step 1 of 4', run.next_step_hint)
        run.state = 'computed'
        self.env['buz.plan.suggestion'].create({
            'run_id': run.id, 'product_id': self.p1.id, 'action': 'buy', 'qty': 1,
            'uom_id': self.p1.uom_id.id, 'date_need': MONDAY, 'date_release': MONDAY,
            'is_late': True, 'vendor_id': self.vendor_a.id})
        self.assertEqual(run.next_step, 'review')
        self.assertIn('Step 2 of 4: review 1 suggestions (1 late)', run.next_step_hint)
        self._wizard(run.suggestion_ids, run=run)._create_documents()
        self.assertEqual(run.next_step, 'schedule')
        self.assertIn('1 blanket orders', run.next_step_hint)
        self.assertIn('Step 3 of 4', run.next_step_hint)

    def test_explanation_adds_up_with_earlier_suggestions(self):
        """The second shortage of a product already includes the first suggested quantity."""
        params = {self.p1.id: {'supply_method': 'buy', 'min_batch_qty': 50}}
        data = self.data(
            self.p1, params=params, onhand={self.p1.id: 10},
            delivery={self.p1.id: self.bk({0: 30, 2: 80})})
        hits = [h for h in solve(data).suggestions if h['product_id'] == self.p1.id]
        self.assertEqual(len(hits), 2)
        second = self._sugg(
            self.p1, hits[1]['qty'], onhand_qty=hits[1]['onhand_qty'], incoming_qty=hits[1]['incoming_qty'],
            demand_qty=hits[1]['demand_qty'], projected_qty=hits[1]['projected_qty'],
            shortage_qty=hits[1]['shortage_qty'])
        self.assertIn('earlier suggestions 50', second.explanation)
        self.assertIn('= %s' % ('%g' % hits[1]['projected_qty']), second.explanation)
        first = self._sugg(
            self.p1, hits[0]['qty'], onhand_qty=hits[0]['onhand_qty'], incoming_qty=hits[0]['incoming_qty'],
            demand_qty=hits[0]['demand_qty'], projected_qty=hits[0]['projected_qty'],
            shortage_qty=hits[0]['shortage_qty'])
        self.assertNotIn('earlier suggestions', first.explanation)
        self.assertIn('On hand 10 + incoming 0 - demand 30 = -20 (short by 20)', first.explanation)

    def test_explanation_sentence(self):
        s = self._sugg(self.p1, 150, onhand_qty=120, incoming_qty=40, demand_qty=300,
                       projected_qty=-140, shortage_qty=140)
        self.assertIn('On hand 120 + incoming 40 - demand 300 = -140', s.explanation)
        self.assertIn('Suggested: buy 150', s.explanation)
        self.assertIn('minimum batch', s.explanation, "150 > 140 short is explained")
