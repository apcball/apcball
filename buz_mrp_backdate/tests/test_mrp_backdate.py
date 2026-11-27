# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMrpBackdate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # No e-mail on purpose: logging the backdate must not require one.
        # Test users have no address; skip local partner required-field rules.
        users = cls.env['res.users'].with_context(
            skip_partner_required_fields=True, no_reset_password=True)

        def user(login, xmlid):
            return users.create({
                'name': login, 'login': login,
                'groups_id': [Command.set([cls.env.ref(xmlid).id])],
            })

        cls.user_full = user('mrp_bd_full', 'buz_mrp_backdate.group_mrp_backdate')
        cls.user_future = user(
            'mrp_bd_future', 'buz_mrp_backdate.group_mrp_backdate_future')
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.component = cls.env['product.product'].create({
            'name': 'Backdate Component', 'type': 'product', 'standard_price': 10.0,
        })
        cls.finished = cls.env['product.product'].create({
            'name': 'Backdate Finished', 'type': 'product', 'standard_price': 10.0,
        })
        cls.bom = cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.finished.product_tmpl_id.id,
            'product_qty': 1.0,
            'bom_line_ids': [Command.create({
                'product_id': cls.component.id, 'product_qty': 1.0,
            })],
        })
        cls.now = fields.Datetime.now().replace(microsecond=0)

    # ------------------------------------------------------------ helpers
    def _redate(self, moves, days_ago):
        date = self.now - timedelta(days=days_ago)
        moves.write({'date': date})
        moves.move_line_ids.write({'date': date})
        self.env.flush_all()

    def _receive_component(self, qty, days_ago):
        stock = self.warehouse.lot_stock_id
        supplier = self.env.ref('stock.stock_location_suppliers')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': supplier.id,
            'location_dest_id': stock.id,
            'move_ids': [Command.create({
                'name': self.component.name,
                'product_id': self.component.id,
                'product_uom_qty': qty,
                'product_uom': self.component.uom_id.id,
                'location_id': supplier.id,
                'location_dest_id': stock.id,
            })],
        })
        picking.action_confirm()
        picking.move_ids.write({'quantity': qty, 'picked': True})
        picking.move_ids._action_done()
        self._redate(picking.move_ids, days_ago)
        return picking

    def _mandatory_analytic_vals(self):
        """Databases may require analytic distribution on manufacturing orders."""
        if 'analytic_distribution' not in self.env['mrp.production']._fields:
            return {}
        plans = self.env['account.analytic.plan'].get_relevant_plans(
            business_domain='manufacturing_order',
            company_id=self.env.company.id)
        distribution = {}
        for plan in plans:
            if plan['applicability'] != 'mandatory':
                continue
            account = self.env['account.analytic.account'].create({
                'name': 'Backdate %s' % plan['id'], 'plan_id': plan['id'],
            })
            distribution[str(account.id)] = 100.0
        return {'analytic_distribution': distribution} if distribution else {}

    def _confirmed_mo(self, qty):
        mo = self.env['mrp.production'].create({
            'product_id': self.finished.id,
            'product_qty': qty,
            'bom_id': self.bom.id,
            # produce and consume where the test receives its components
            'picking_type_id': self.warehouse.manu_type_id.id,
            'location_src_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
            **self._mandatory_analytic_vals(),
        })
        mo.action_confirm()
        return mo

    def _done_mo(self, qty, days_ago):
        mo = self._confirmed_mo(qty)
        mo.qty_producing = qty
        mo._set_qty_producing()
        mo.move_raw_ids.write({'picked': True})
        mo.with_context(
            skip_backorder=True, skip_consumption=True).button_mark_done()
        self.assertEqual(mo.state, 'done')
        self._redate(mo.move_raw_ids | mo.move_finished_ids, days_ago)
        return mo

    def _done_unbuild(self, mo, qty, days_ago):
        unbuild = self.env['mrp.unbuild'].create({
            'mo_id': mo.id,
            'product_id': self.finished.id,
            'bom_id': self.bom.id,
            'product_qty': qty,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
        })
        # buz_unbuild_state_guard (when installed) only allows its own entry point
        if hasattr(unbuild, 'action_direct_unbuild'):
            unbuild.action_direct_unbuild()
        else:
            unbuild.action_unbuild()
        self.assertEqual(unbuild.state, 'done')
        self._redate(unbuild.consume_line_ids | unbuild.produce_line_ids, days_ago)
        return unbuild

    def _wizard(self, record, days_ago, user=None, remark='count correction'):
        field = ('production_id' if record._name == 'mrp.production'
                 else 'unbuild_id')
        return self.env['mrp.backdate.wizard'].with_user(
            user or self.user_full).create({
                field: record.id,
                'backdate': self.now - timedelta(days=days_ago),
                'backdate_remark': remark,
            })

    def _dates(self, moves):
        """Dates as stored in the database (the module writes them with SQL)."""
        self.env.flush_all()
        self.env.invalidate_all()
        return set(moves.mapped('date')) | set(moves.move_line_ids.mapped('date'))

    def _change_text(self, record, old, new):
        """The "old → new" text as the log shows it to the full user."""
        def shown(value):
            return fields.Datetime.context_timestamp(
                record.with_user(self.user_full), value).strftime(
                    '%d/%m/%Y %H:%M:%S')
        return '%s → %s' % (shown(old), shown(new))

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].set_param(
            'stock_picking_backdate_all.negative_stock_mode', 'block')

    def _backdate_logs(self, record):
        return record.message_ids.filtered(lambda m: 'Backdate' in (m.body or ''))

    # ------------------------------------------------------------ groups
    def test_full_group_implies_future_group(self):
        self.assertTrue(self.user_full.has_group(
            'buz_mrp_backdate.group_mrp_backdate_future'))
        self.assertFalse(self.user_future.has_group(
            'buz_mrp_backdate.group_mrp_backdate'))
        self.assertTrue(self.user_future.has_group('mrp.group_mrp_user'))

    def test_future_group_blocks_past(self):
        self._receive_component(5, days_ago=20)
        mo = self._done_mo(2, days_ago=10)
        with self.assertRaisesRegex(UserError, 'Past & Future'):
            self._wizard(mo, 12, user=self.user_future).action_apply_backdate()
        self.assertFalse(mo.backdate)

    def test_future_group_allows_future(self):
        self._receive_component(5, days_ago=20)
        mo = self._done_mo(2, days_ago=10)
        self._wizard(mo, -1, user=self.user_future).action_apply_backdate()
        self.assertEqual(
            self._dates(mo.move_raw_ids), {self.now + timedelta(days=1)})

    # ------------------------------------------------------------ MO
    def test_unfinished_mo_is_blocked(self):
        mo = self._confirmed_mo(1)
        with self.assertRaises(UserError):
            self._wizard(mo, 5).action_apply_backdate()
        self.assertFalse(mo.backdate)

    def test_mo_backdate_updates_dates(self):
        self._receive_component(5, days_ago=20)
        mo = self._done_mo(2, days_ago=5)
        self._wizard(mo, 10).action_apply_backdate()
        new = self.now - timedelta(days=10)
        moves = mo.move_raw_ids | mo.move_finished_ids
        self.assertEqual(self._dates(moves), {new})
        self.assertEqual(mo.date_finished, new)
        layers = self.env['stock.valuation.layer'].search(
            [('stock_move_id', 'in', moves.ids)])
        self.assertTrue(layers)
        self.assertEqual(set(layers.mapped('accounting_date')), {new})

    def test_mo_backdate_before_component_receipt_is_blocked(self):
        self._receive_component(5, days_ago=10)
        mo = self._done_mo(2, days_ago=5)
        moves = mo.move_raw_ids | mo.move_finished_ids
        old = self._dates(moves)
        old_finished = mo.date_finished
        with self.assertRaisesRegex(UserError, 'Backdate Component'):
            self._wizard(mo, 15).action_apply_backdate()
        self.assertEqual(self._dates(moves), old)
        self.assertEqual(mo.date_finished, old_finished)
        self.assertFalse(mo.backdate)
        self.assertFalse(self._backdate_logs(mo))

    def test_mo_backdate_is_logged_in_chatter(self):
        self._receive_component(5, days_ago=20)
        mo = self._done_mo(2, days_ago=5)
        old_date = mo.date_finished
        self.assertTrue(old_date)
        self._wizard(mo, 10, remark='<b>fix</b> & check').action_apply_backdate()
        log = self._backdate_logs(mo)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.author_id, self.user_full.partner_id)
        self.assertEqual(log.subtype_id, self.env.ref('mail.mt_note'))
        body = str(log.body)
        self.assertIn('&lt;b&gt;fix&lt;/b&gt; &amp; check', body)
        self.assertNotIn('<b>fix</b>', body)
        self.assertIn(self._change_text(
            mo, old_date, self.now - timedelta(days=10)), body)

    # ------------------------------------------------------------ unbuild
    def test_unbuild_backdate_updates_dates_and_logs(self):
        self._receive_component(5, days_ago=20)
        mo = self._done_mo(2, days_ago=15)
        unbuild = self._done_unbuild(mo, 1, days_ago=5)
        self._wizard(unbuild, 10).action_apply_backdate()
        moves = unbuild.consume_line_ids | unbuild.produce_line_ids
        self.assertEqual(self._dates(moves), {self.now - timedelta(days=10)})
        log = self._backdate_logs(unbuild)
        self.assertEqual(len(log), 1)
        self.assertIn('count correction', str(log.body))
        self.assertIn(self._change_text(
            unbuild, self.now - timedelta(days=5), self.now - timedelta(days=10)),
            str(log.body))

    def test_unbuild_backdate_before_production_is_blocked(self):
        self._receive_component(5, days_ago=20)
        mo = self._done_mo(2, days_ago=10)
        unbuild = self._done_unbuild(mo, 1, days_ago=5)
        moves = unbuild.consume_line_ids | unbuild.produce_line_ids
        old = self._dates(moves)
        with self.assertRaisesRegex(UserError, 'Backdate Finished'):
            self._wizard(unbuild, 12).action_apply_backdate()
        self.assertEqual(self._dates(moves), old)
        self.assertFalse(unbuild.backdate)
        self.assertFalse(self._backdate_logs(unbuild))

    def test_negative_backdate_is_allowed_and_logged_by_default(self):
        self.env['ir.config_parameter'].set_param(
            'stock_picking_backdate_all.negative_stock_mode', False)
        self._receive_component(5, days_ago=10)
        mo = self._done_mo(2, days_ago=5)
        self._wizard(mo, 15).action_apply_backdate()
        self.assertEqual(
            self._dates(mo.move_raw_ids), {self.now - timedelta(days=15)})
        log = self._backdate_logs(mo)
        self.assertEqual(len(log), 1)
        self.assertIn('Backdate Component', str(log.body))
