from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import common


class TestOfficeSupplyRequisition(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.manager_group = self.env.ref('office_supply_requisition.group_office_supply_manager')
        self.manager = self.env['res.users'].create({
            'name': 'Office Supply Manager',
            'login': 'office_supply_manager_test',
            'email': 'manager@test.com',
            'groups_id': [(6, 0, [self.manager_group.id])],
        })
        self.warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        self.assertTrue(self.warehouse, 'Warehouse should exist for stock validation tests')
        self.location = self.warehouse.lot_stock_id
        self.product = self.env['product.product'].create({
            'name': 'Office Paper',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
        })
        self.env['stock.quant']._update_available_quantity(self.product, self.location, 10.0)
        self.employee = self.env.user.employee_id or self.env['hr.employee'].create({
            'name': 'Test Employee',
            'user_id': self.env.user.id,
        })

    def _create_requisition(self, qty=2.0):
        requisition = self.env['office.supply.requisition'].create({
            'employee_id': self.employee.id,
            'requester_id': self.employee.id,
            'receiver_id': self.employee.id,
            'location_id': self.location.id,
            'date': fields.Datetime.now(),
        })
        requisition.line_ids = [(0, 0, {
            'product_id': self.product.id,
            'product_uom_qty': qty,
        })]
        return requisition

    def test_submit_requires_at_least_one_line(self):
        requisition = self.env['office.supply.requisition'].create({
            'employee_id': self.employee.id,
            'requester_id': self.employee.id,
            'receiver_id': self.employee.id,
            'location_id': self.location.id,
            'date': fields.Datetime.now(),
        })
        with self.assertRaises(UserError):
            requisition.action_submit()

    def test_submit_sets_state_to_confirmed(self):
        requisition = self._create_requisition(qty=3.0)
        requisition.action_submit()
        self.assertEqual(requisition.state, 'confirmed')

    def test_sign_and_confirm_success_when_stock_is_available(self):
        requisition = self._create_requisition(qty=3.0)
        requisition.requester_id = self.employee
        requisition.receiver_id = self.employee
        requisition.action_submit()
        requisition.signature = b'test-signature'
        requisition.action_sign_and_confirm()
        self.assertEqual(requisition.state, 'done')

    def test_confirm_rejects_over_stock_request(self):
        requisition = self._create_requisition(qty=15.0)
        requisition.requester_id = self.employee
        requisition.receiver_id = self.employee
        requisition.action_submit()
        requisition.signature = b'test-signature'
        with self.assertRaises(UserError):
            requisition.action_sign_and_confirm()

    def test_reset_draft_restores_stock(self):
        requisition = self._create_requisition(qty=4.0)
        requisition.requester_id = self.employee
        requisition.receiver_id = self.employee
        requisition.action_submit()
        requisition.signature = b'test-signature'
        requisition.action_sign_and_confirm()
        requisition.action_reset_draft()
        self.assertEqual(requisition.state, 'draft')
        self.assertEqual(
            self.product.with_context(location=self.location.id).qty_available,
            10.0,
        )

    def test_duplicate_product_in_same_requisition_is_forbidden(self):
        requisition = self.env['office.supply.requisition'].create({
            'employee_id': self.employee.id,
            'requester_id': self.employee.id,
            'receiver_id': self.employee.id,
            'location_id': self.location.id,
            'date': fields.Datetime.now(),
        })
        self.env['office.supply.requisition.line'].create({
            'requisition_id': requisition.id,
            'product_id': self.product.id,
            'product_uom_qty': 2.0,
        })
        with self.assertRaises(UserError):
            self.env['office.supply.requisition.line'].create({
                'requisition_id': requisition.id,
                'product_id': self.product.id,
                'product_uom_qty': 1.0,
            })

    def test_zero_or_negative_quantity_is_forbidden(self):
        with self.assertRaises(UserError):
            self.env['office.supply.requisition.line'].create({
                'requisition_id': self._create_requisition(qty=1.0).id,
                'product_id': self.product.id,
                'product_uom_qty': 0.0,
            })

    def test_done_record_cannot_be_edited_or_deleted(self):
        requisition = self._create_requisition(qty=2.0)
        requisition.action_submit()
        requisition.signature = b'test-signature'
        requisition.action_sign_and_confirm()
        with self.assertRaises(UserError):
            requisition.write({'employee_id': self.employee.id})
        with self.assertRaises(UserError):
            requisition.unlink()
