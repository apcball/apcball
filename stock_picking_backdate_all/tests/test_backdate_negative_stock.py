# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBackdateNegativeStock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Test users have no address; skip local partner required-field rules.
        users = cls.env['res.users'].with_context(
            skip_partner_required_fields=True, no_reset_password=True)
        cls.user = users.create({
            'name': 'Backdate Stock', 'login': 'bd_stock',
            'groups_id': [Command.set([
                cls.env.ref('stock.group_stock_user').id,
                cls.env.ref(
                    'stock_picking_backdate_all.stock_picking_backdate_assign_group').id,
            ])],
        })
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'Backdate Product', 'type': 'product', 'standard_price': 10.0,
        })
        cls.now = fields.Datetime.now().replace(microsecond=0)

    def _ready_picking(self, incoming, qty):
        picking_type = (self.warehouse.in_type_id if incoming
                        else self.warehouse.out_type_id)
        stock = self.warehouse.lot_stock_id
        outside = self.env.ref(
            'stock.stock_location_suppliers' if incoming
            else 'stock.stock_location_customers')
        source, dest = (outside, stock) if incoming else (stock, outside)
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'move_ids': [Command.create({
                'name': self.product.name,
                'product_id': self.product.id,
                'product_uom_qty': qty,
                'product_uom': self.product.uom_id.id,
                'location_id': source.id,
                'location_dest_id': dest.id,
            })],
        })
        picking.action_confirm()
        return picking

    def _picking(self, incoming, qty, days_ago):
        picking = self._ready_picking(incoming, qty)
        picking.move_ids.write({'quantity': qty, 'picked': True})
        picking.move_ids._action_done()
        self.assertEqual(picking.state, 'done')
        date = self.now - timedelta(days=days_ago)
        picking.move_ids.write({'date': date})
        picking.move_line_ids.write({'date': date})
        return picking

    def _wizard(self, pickings, days_ago):
        return self.env['stock.picking.backdate.wiz'].with_user(self.user).create({
            'date': self.now - timedelta(days=days_ago),
            'picking_ids': [Command.set(pickings.ids)],
        })

    def test_delivery_before_receipt_is_blocked_and_nothing_changes(self):
        self._picking(True, 5, days_ago=10)
        delivery = self._picking(False, 5, days_ago=2)
        old_date = delivery.move_ids.date
        with self.assertRaises(UserError):
            self._wizard(delivery, 20).change_to_backdate()
        self.assertEqual(delivery.move_ids.date, old_date)

    def test_delivery_after_receipt_is_allowed(self):
        self._picking(True, 5, days_ago=10)
        delivery = self._picking(False, 5, days_ago=2)
        self._wizard(delivery, 5)._check_backdate_negative_stock()

    def test_receipt_moved_after_delivery_is_blocked(self):
        receipt = self._picking(True, 5, days_ago=10)
        self._picking(False, 5, days_ago=5)
        with self.assertRaises(UserError):
            self._wizard(receipt, 1)._check_backdate_negative_stock()

    def test_selected_pickings_are_checked_together(self):
        receipt = self._picking(True, 5, days_ago=10)
        delivery = self._picking(False, 5, days_ago=5)
        self._wizard(receipt | delivery, 20)._check_backdate_negative_stock()

    def test_unfinished_picking_is_blocked_and_nothing_changes(self):
        receipt = self._ready_picking(True, 5)
        self.assertNotEqual(receipt.state, 'done')
        old_scheduled = receipt.scheduled_date
        old_date = receipt.move_ids.date
        with self.assertRaisesRegex(UserError, receipt.name):
            self._wizard(receipt, 5).change_to_backdate()
        self.assertEqual(receipt.scheduled_date, old_scheduled)
        self.assertEqual(receipt.move_ids.date, old_date)
        self.assertFalse(receipt.date_done)

    def test_one_unfinished_picking_blocks_whole_selection(self):
        done = self._picking(True, 5, days_ago=10)
        ready = self._ready_picking(True, 5)
        old_date = done.move_ids.date
        with self.assertRaisesRegex(UserError, ready.name):
            self._wizard(done | ready, 5).change_to_backdate()
        self.assertEqual(done.move_ids.date, old_date)

    def test_cancelled_picking_is_blocked(self):
        receipt = self._ready_picking(True, 5)
        receipt.action_cancel()
        with self.assertRaisesRegex(UserError, receipt.name):
            self._wizard(receipt, 5).change_to_backdate()

    def test_allowed_change_updates_dates(self):
        self._picking(True, 5, days_ago=10)
        delivery = self._picking(False, 5, days_ago=2)
        self._wizard(delivery, 5).change_to_backdate()
        new_date = self.now - timedelta(days=5)
        self.assertEqual(delivery.date_done, new_date)
        self.assertEqual(delivery.move_ids.date, new_date)
        self.assertEqual(delivery.move_line_ids.date, new_date)
