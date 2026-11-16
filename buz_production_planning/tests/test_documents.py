# pylint: disable=protected-access  # tests exercise internal entry points
from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import MONDAY, PlanCommon


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

    def _wizard(self, suggestions):
        return self.env['buz.plan.create.documents.wizard'].create({
            'run_id': self.run_.id, 'suggestion_ids': [Command.set(suggestions.ids)]})

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
        result = self._wizard(s1 | s2 | s3)._create_documents()
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
        result = self._wizard(ok | bad)._create_documents()
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
        self._wizard(b)._create_documents()
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
            'run_id': self.run_.id, 'suggestion_ids': [Command.set((s | b).ids)]})
        result = wiz._create_documents()
        self.assertEqual((len(result['productions']), len(result['orders'])), (1, 1))

    def test_smart_button_on_mo(self):
        s = self._sugg(self.fg)
        mo = self._wizard(s)._create_documents()['productions']
        self.assertEqual(mo.buz_plan_run_id, self.run_)
        self.assertEqual(mo.action_open_buz_plan()['res_id'], self.run_.id)
