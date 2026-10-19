# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBackdateGroups(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_full = cls.env.ref(
            'stock_picking_backdate_all.stock_picking_backdate_assign_group')
        group_future = cls.env.ref(
            'stock_picking_backdate_all.stock_picking_backdate_future_group')
        base_groups = [cls.env.ref('stock.group_stock_user').id]
        cls.user_full = cls.env['res.users'].create({
            'name': 'Backdate Full', 'login': 'bd_full',
            'groups_id': [(6, 0, base_groups + [group_full.id])],
        })
        cls.user_future = cls.env['res.users'].create({
            'name': 'Backdate Future', 'login': 'bd_future',
            'groups_id': [(6, 0, base_groups + [group_future.id])],
        })

    def _wizard(self, user, delta_days):
        return self.env['stock.picking.backdate.wiz'].with_user(user).create({
            'date': fields.Datetime.now() + timedelta(days=delta_days),
        })

    def test_full_implies_future(self):
        self.assertTrue(self.user_full.has_group(
            'stock_picking_backdate_all.stock_picking_backdate_future_group'))
        self.assertFalse(self.user_future.has_group(
            'stock_picking_backdate_all.stock_picking_backdate_assign_group'))

    def test_full_can_use_past_and_future(self):
        self._wizard(self.user_full, -5)._check_backdate_allowed()
        self._wizard(self.user_full, 5)._check_backdate_allowed()

    def test_future_group_allows_today_and_future(self):
        self._wizard(self.user_future, 0)._check_backdate_allowed()
        self._wizard(self.user_future, 5)._check_backdate_allowed()

    def test_future_group_blocks_past(self):
        with self.assertRaises(UserError):
            self._wizard(self.user_future, -2).change_to_backdate()
