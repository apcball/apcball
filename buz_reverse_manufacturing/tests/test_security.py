# Part of buz addons for Mogen Co. See LICENSE file.
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ReverseManufacturingCommon


@tagged('post_install', '-at_install')
class TestSecurity(ReverseManufacturingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_operator = cls.env['res.users'].create({
            'name': 'RMO Operator',
            'login': 'rmo_operator',
            'email': 'rmo_operator@test.example.com',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref(
                    'buz_reverse_manufacturing.group_reverse_mfg_user').id,
            ])],
        })
        cls.user_manager = cls.env['res.users'].create({
            'name': 'RMO Manager',
            'login': 'rmo_manager',
            'email': 'rmo_manager@test.example.com',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref(
                    'buz_reverse_manufacturing.group_reverse_mfg_manager').id,
            ])],
        })
        cls.user_mrp_only = cls.env['res.users'].create({
            'name': 'MRP Only',
            'login': 'rmo_mrp_only',
            'email': 'rmo_mrp_only@test.example.com',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('mrp.group_mrp_user').id,
            ])],
        })

    def test_user_can_create_lines(self):
        rmo = self._create_rmo()
        line = rmo.recovery_line_ids[0]
        line.with_user(self.user_operator).write({'actual_qty': 0.5})
        self.assertEqual(line.actual_qty, 0.5)

    def test_user_cannot_unlink_lines(self):
        rmo = self._create_rmo()
        with self.assertRaises(AccessError):
            rmo.recovery_line_ids[0].with_user(self.user_operator).unlink()

    def test_manager_can_unlink_lines(self):
        rmo = self._create_rmo()
        rmo.recovery_line_ids[0].with_user(self.user_manager).unlink()
        self.assertEqual(len(rmo.recovery_line_ids), 2)

    def test_mrp_only_user_readonly(self):
        rmo = self._create_rmo()
        line = rmo.recovery_line_ids[0]
        # can read
        line.with_user(self.user_mrp_only).read(['product_id'])
        # cannot write
        with self.assertRaises(AccessError):
            line.with_user(self.user_mrp_only).write({'actual_qty': 9.0})

    def test_groups_implication(self):
        self.assertIn(
            self.env.ref('buz_reverse_manufacturing.group_reverse_mfg_user'),
            self.user_manager.groups_id,
            'Manager group must imply user group')
