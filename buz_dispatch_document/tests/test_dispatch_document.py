from datetime import timedelta

from odoo import fields
from odoo.tests import common, tagged
from odoo.exceptions import UserError


@tagged('at_install', 'post_install')
class TestDispatchDocument(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create a product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product - Dispatch Document',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })

        # Create a partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer - Dispatch Document',
        })

        # Create a warehouse and picking type
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        # Get picking type for delivery orders
        cls.picking_type_out = cls.warehouse.out_type_id

        # Create a location for stock
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref('stock.stock_location_customers')

        # Create stock quant
        cls.env['stock.quant'].create({
            'product_id': cls.product.id,
            'location_id': cls.stock_location.id,
            'quantity': 100.0,
        })

        # Create a stock picking (simulating DO from SO)
        cls.picking = cls.env['stock.picking'].create({
            'picking_type_id': cls.picking_type_out.id,
            'partner_id': cls.partner.id,
            'location_id': cls.stock_location.id,
            'location_dest_id': cls.customer_location.id,
        })

        # Create a move line
        cls.move = cls.env['stock.move'].create({
            'name': cls.product.display_name,
            'product_id': cls.product.id,
            'product_uom_qty': 10.0,
            'product_uom': cls.product.uom_id.id,
            'picking_id': cls.picking.id,
            'location_id': cls.stock_location.id,
            'location_dest_id': cls.customer_location.id,
            'quantity': 10.0,
            'state': 'draft',
        })

        # Confirm and assign picking to get to 'assigned' state
        cls.picking.action_confirm()
        cls.move.quantity = 10.0
        cls.move.picked = True
        cls.picking.action_assign()

    def test_01_create_draft(self):
        """Test creating a dispatch document in draft state"""
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        self.assertEqual(doc.state, 'draft')
        self.assertFalse(doc.name)
        expected_date = fields.Date.today() + timedelta(days=1)
        self.assertEqual(doc.document_date, expected_date)

    def test_02_confirm_runs_sequence(self):
        """Test confirm runs sequence number and sets state"""
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        self.assertEqual(doc.state, 'confirmed')
        self.assertTrue(doc.name)
        self.assertTrue(doc.name.startswith('DD/'))

    def test_03_validate_after_confirm(self):
        """Test validate action validates source DO and sets state to done"""
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        doc.action_validate()
        self.assertEqual(doc.state, 'done')
        self.assertEqual(doc.stock_picking_id.state, 'done')

    def test_04_confirm_twice_raises_error(self):
        """Test cannot confirm an already confirmed document"""
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        with self.assertRaises(UserError):
            doc.action_confirm()

    def test_05_validate_draft_raises_error(self):
        """Test cannot validate a draft document"""
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        with self.assertRaises(UserError):
            doc.action_validate()

    def test_06_set_draft_from_confirmed(self):
        """Test resetting confirmed document back to draft"""
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        self.assertEqual(doc.state, 'confirmed')
        doc.action_set_draft()
        self.assertEqual(doc.state, 'draft')

    def test_07_set_draft_from_done_raises_error(self):
        """Test cannot reset a done document to draft"""
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        doc.action_validate()
        with self.assertRaises(UserError):
            doc.action_set_draft()

    def test_08_cron_validates_due_documents(self):
        """Test cron validates confirmed documents where date <= today"""
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
            'document_date': fields.Date.today() - timedelta(days=1),
        })
        doc.action_confirm()
        self.assertEqual(doc.state, 'confirmed')

        self.env['buz.dispatch.document'].action_validate_cron()
        self.assertEqual(doc.state, 'done')
        self.assertEqual(doc.stock_picking_id.state, 'done')

    def test_09_cron_skips_future_documents(self):
        """Test cron does NOT validate documents with future dates"""
        picking2 = self._create_picking()
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': picking2.id,
            'document_date': fields.Date.today() + timedelta(days=3),
        })
        doc.action_confirm()

        self.env['buz.dispatch.document'].action_validate_cron()
        self.assertEqual(doc.state, 'confirmed')
        self.assertEqual(doc.stock_picking_id.state, 'confirmed')

    def _create_picking(self):
        """Helper to create an additional picking"""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type_out.id,
            'partner_id': self.partner.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.customer_location.id,
        })
        move = self.env['stock.move'].create({
            'name': self.product.display_name,
            'product_id': self.product.id,
            'product_uom_qty': 5.0,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.customer_location.id,
            'quantity': 5.0,
            'state': 'draft',
        })
        picking.action_confirm()
        move.quantity = 5.0
        move.picked = True
        picking.action_assign()
        return picking