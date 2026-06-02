# -*- coding: utf-8 -*-

from odoo import fields
from odoo.tests import tagged, TransactionCase


@tagged('-at_install', 'post_install')
class TestServiceReceiptClaim(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create partner for testing
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Claim Customer - TestServiceReceiptClaim',
            'phone': '0812345678',
        })

        # Create products (no tax)
        cls.product_original = cls.env['product.product'].create({
            'name': 'Test Original Product - Claim',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })
        cls.product_replacement = cls.env['product.product'].create({
            'name': 'Test Replacement Product - Claim',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })

    def _create_receipt(self, case_type='replacement'):
        """Helper to create a service receipt."""
        return self.env['service.receipt'].with_context(tracking_disable=True).create({
            'partner_id': self.partner.id,
            'requester_name': 'Test Requester',
            'service_case_type': case_type,
            'request_date': fields.Date.today(),
            'line_ids': [(0, 0, {
                'product_id': self.product_original.id,
                'quantity': 1.0,
                'resolution_type': 'replace',
                'replacement_product_id': self.product_replacement.id,
                'replacement_qty': 1.0,
            })],
        })

    def test_01_claim_workflow_full(self):
        """Full replacement claim workflow: draft → confirm → return picking → replacement delivery → done."""
        receipt = self._create_receipt('replacement')

        # Initially draft
        self.assertEqual(receipt.state, 'draft')
        self.assertEqual(receipt.service_case_type, 'replacement')

        # Confirm
        receipt.action_confirm()
        self.assertEqual(receipt.state, 'confirmed')

        # Start replacement flow → product_return
        receipt.action_waiting_replacement()
        self.assertEqual(receipt.state, 'product_return')
        self.assertTrue(receipt.claim_number)
        self.assertNotEqual(receipt.claim_number, 'New')

        # Create return picking
        receipt.action_create_return_picking()
        self.assertTrue(receipt.return_picking_id)
        self.assertEqual(receipt.return_picking_id.state, 'assigned')
        self.assertEqual(len(receipt.return_picking_id.move_ids), 1)
        self.assertEqual(receipt.return_picking_id.move_ids[0].product_id.id, self.product_original.id)

        # Validate return
        move = receipt.return_picking_id.move_ids
        move._set_quantity_done(move.product_uom_qty)
        receipt.return_picking_id.button_validate()
        self.assertEqual(receipt.return_picking_id.state, 'done')

        # Create replacement delivery (move from stock to customer)
        receipt.action_create_replacement_picking()
        self.assertTrue(receipt.replacement_picking_id)
        self.assertEqual(len(receipt.replacement_picking_id.move_ids), 1)
        self.assertEqual(receipt.replacement_picking_id.move_ids[0].product_id.id, self.product_replacement.id)
        self.assertEqual(receipt.state, 'replacement_delivery')

        # Validate replacement
        move2 = receipt.replacement_picking_id.move_ids
        move2._set_quantity_done(move2.product_uom_qty)
        receipt.replacement_picking_id.button_validate()
        self.assertEqual(receipt.replacement_picking_id.state, 'done')

        # Done
        receipt.action_done()
        self.assertEqual(receipt.state, 'done')

    def test_02_return_picking_no_lines(self):
        """Error when creating return picking without replace lines."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        receipt.action_waiting_replacement()

        # Remove product from lines
        receipt.line_ids.write({'product_id': False})

        with self.assertRaises(Exception):
            receipt.action_create_return_picking()

    def test_03_replacement_picking_no_lines(self):
        """Error when creating replacement picking without replacement product."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        receipt.action_waiting_replacement()
        receipt.action_create_return_picking()

        # Remove replacement product
        receipt.line_ids.write({'replacement_product_id': False})

        with self.assertRaises(Exception):
            receipt.action_create_replacement_picking()

    def test_04_create_sale_order(self):
        """Create sale order for chargeable service."""
        receipt = self._create_receipt('service')
        receipt.write({
            'charge_customer': True,
        })
        receipt.line_ids.write({
            'bill_customer': True,
            'price_unit': 500.0,
        })
        receipt.action_confirm()

        # Create sale order
        receipt.action_create_sale_order()
        self.assertTrue(receipt.sale_order_id)
        self.assertEqual(len(receipt.sale_order_id.order_line), 1)
        self.assertEqual(receipt.sale_order_id.order_line[0].price_unit, 500.0)
        self.assertEqual(receipt.sale_order_id.partner_id.id, self.partner.id)

        # View sale order
        action = receipt.action_view_sale_order()
        self.assertEqual(action['res_id'], receipt.sale_order_id.id)

    def test_05_view_actions(self):
        """View actions for pickings and sale order."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        receipt.action_waiting_replacement()
        receipt.action_create_return_picking()

        # View return
        action = receipt.action_view_return_picking()
        self.assertEqual(action['res_id'], receipt.return_picking_id.id)

        # View pickings
        action_pick = receipt.action_view_pickings()
        self.assertEqual(action_pick['res_model'], 'stock.picking')

    def test_06_picking_counts(self):
        """Compute fields for picking counts."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        receipt.action_waiting_replacement()

        # No pickings yet
        self.assertEqual(receipt.return_picking_count, 0)
        self.assertEqual(receipt.replacement_picking_count, 0)
        self.assertEqual(receipt.picking_count, 0)

        # Create return
        receipt.action_create_return_picking()
        self.assertEqual(receipt.return_picking_count, 1)
        self.assertEqual(receipt.picking_count, 1)

        # Create replacement
        receipt.action_create_replacement_picking()
        self.assertEqual(receipt.replacement_picking_count, 1)
        self.assertEqual(receipt.picking_count, 2)

    def test_07_cancel_draft(self):
        """Cancel and reset to draft."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        self.assertEqual(receipt.state, 'confirmed')

        receipt.action_cancel()
        self.assertEqual(receipt.state, 'cancel')

        receipt.action_draft()
        self.assertEqual(receipt.state, 'draft')