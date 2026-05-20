# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestMrpStockRequest(TransactionCase):
    """Test MRP Stock Request module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.StockRequest = cls.env['mrp.stock.request']
        cls.Product = cls.env['product.product']
        cls.Location = cls.env['stock.location']
        cls.PickingType = cls.env['stock.picking.type']

        # Create test locations
        cls.location_src = cls.Location.create({
            'name': 'Test Source',
            'usage': 'internal',
        })
        cls.location_dest = cls.Location.create({
            'name': 'Test Dest',
            'usage': 'internal',
        })

        # Find internal picking type
        cls.picking_type = cls.PickingType.search([
            ('code', '=', 'internal'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        # Create test storable product
        cls.product = cls.Product.create({
            'name': 'Test Component',
            'type': 'product',
        })

    def test_01_create_stock_request(self):
        """Test basic stock request creation."""
        request = self.StockRequest.create({
            'picking_type_id': self.picking_type.id,
            'location_id': self.location_src.id,
            'location_dest_id': self.location_dest.id,
            'company_id': self.env.company.id,
        })
        self.assertTrue(request.name)
        self.assertEqual(request.state, 'draft')

    def test_02_confirm_without_lines(self):
        """Test that confirming without lines raises error."""
        request = self.StockRequest.create({
            'picking_type_id': self.picking_type.id,
            'location_id': self.location_src.id,
            'location_dest_id': self.location_dest.id,
            'company_id': self.env.company.id,
        })
        with self.assertRaises(UserError):
            request.action_confirm_with_validation()

    def test_03_confirm_with_lines(self):
        """Test confirming a request with lines creates picking."""
        request = self.StockRequest.create({
            'picking_type_id': self.picking_type.id,
            'location_id': self.location_src.id,
            'location_dest_id': self.location_dest.id,
            'company_id': self.env.company.id,
        })
        self.env['mrp.stock.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'uom_id': self.product.uom_id.id,
            'qty_requested': 10.0,
        })
        request.action_confirm_with_validation()
        self.assertEqual(request.state, 'requested')
        self.assertTrue(request.picking_ids)

    def test_04_cancel_from_requested(self):
        """Test cancelling from requested state."""
        request = self.StockRequest.create({
            'picking_type_id': self.picking_type.id,
            'location_id': self.location_src.id,
            'location_dest_id': self.location_dest.id,
            'company_id': self.env.company.id,
        })
        self.env['mrp.stock.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'uom_id': self.product.uom_id.id,
            'qty_requested': 5.0,
        })
        request.action_confirm_with_validation()
        request.action_cancel()
        self.assertEqual(request.state, 'cancel')

    def test_05_reset_to_draft(self):
        """Test resetting cancelled request to draft."""
        request = self.StockRequest.create({
            'picking_type_id': self.picking_type.id,
            'location_id': self.location_src.id,
            'location_dest_id': self.location_dest.id,
            'company_id': self.env.company.id,
        })
        request.action_cancel()
        self.assertEqual(request.state, 'cancel')
        request.action_draft()
        self.assertEqual(request.state, 'draft')

    def test_06_line_qty_remaining(self):
        """Test line quantity remaining computation."""
        request = self.StockRequest.create({
            'picking_type_id': self.picking_type.id,
            'location_id': self.location_src.id,
            'location_dest_id': self.location_dest.id,
            'company_id': self.env.company.id,
        })
        line = self.env['mrp.stock.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'uom_id': self.product.uom_id.id,
            'qty_requested': 100.0,
        })
        self.assertEqual(line.qty_remaining, 100.0)
        self.assertEqual(line.qty_issued, 0.0)

    def test_07_sequence_generation(self):
        """Test that sequence is generated on create."""
        request = self.StockRequest.create({
            'picking_type_id': self.picking_type.id,
            'location_id': self.location_src.id,
            'location_dest_id': self.location_dest.id,
            'company_id': self.env.company.id,
        })
        self.assertTrue(request.name.startswith('SRQ/'))
