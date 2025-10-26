# -*- coding: utf-8 -*-
from odoo.tests import common


class TestMultiProductRMA(common.TransactionCase):
    
    def setUp(self):
        super(TestMultiProductRMA, self).setUp()
        
        # Create test data
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer',
            'is_company': True,
        })
        
        self.product1 = self.env['product.product'].create({
            'name': 'Test Product 1',
            'type': 'product',
            'tracking': 'lot',
        })
        
        self.product2 = self.env['product.product'].create({
            'name': 'Test Product 2',
            'type': 'product',
            'tracking': 'none',
        })
        
        self.lot1 = self.env['stock.lot'].create({
            'name': 'LOT001',
            'product_id': self.product1.id,
            'company_id': self.env.company.id,
        })
        
        # Create warranty card
        self.warranty_card = self.env['warranty.card'].create({
            'partner_id': self.partner.id,
            'product_id': self.product1.id,
            'lot_id': self.lot1.id,
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        })
        
        # Create warranty claim
        self.claim = self.env['warranty.claim'].create({
            'warranty_card_id': self.warranty_card.id,
            'partner_id': self.partner.id,
            'product_id': self.product1.id,
            'lot_id': self.lot1.id,
            'claim_type': 'repair',
            'description': 'Test claim for multi-product RMA',
        })
        
        # Configure RMA settings
        self.env['ir.config_parameter'].sudo().set_param(
            'buz_warranty_management.warranty_rma_in_picking_type_id',
            self.env.ref('stock.picking_type_in').id
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'buz_warranty_management.warranty_repair_location_id',
            self.env.ref('stock.stock_location_stock').id
        )
    
    def test_multi_product_rma_wizard_creation(self):
        """Test that the multi-product RMA wizard can be created with multiple lines"""
        # Create wizard
        wizard = self.env['warranty.rma.receive.wizard'].with_context({
            'default_claim_id': self.claim.id,
            'default_partner_id': self.partner.id,
        }).create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            'line_ids': [
                (0, 0, {
                    'product_id': self.product1.id,
                    'lot_id': self.lot1.id,
                    'qty': 1.0,
                    'reason': 'Defective component',
                }),
                (0, 0, {
                    'product_id': self.product2.id,
                    'qty': 2.0,
                    'reason': 'Missing accessories',
                }),
            ],
        })
        
        # Verify wizard creation
        self.assertEqual(len(wizard.line_ids), 2)
        self.assertEqual(wizard.line_ids[0].product_id, self.product1)
        self.assertEqual(wizard.line_ids[1].product_id, self.product2)
        self.assertEqual(wizard.line_ids[0].qty, 1.0)
        self.assertEqual(wizard.line_ids[1].qty, 2.0)
    
    def test_multi_product_rma_picking_creation(self):
        """Test that multi-product RMA creates correct picking with multiple moves"""
        # Create wizard
        wizard = self.env['warranty.rma.receive.wizard'].with_context({
            'default_claim_id': self.claim.id,
            'default_partner_id': self.partner.id,
        }).create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            'line_ids': [
                (0, 0, {
                    'product_id': self.product1.id,
                    'lot_id': self.lot1.id,
                    'qty': 1.0,
                    'reason': 'Defective component',
                }),
                (0, 0, {
                    'product_id': self.product2.id,
                    'qty': 2.0,
                    'reason': 'Missing accessories',
                }),
            ],
        })
        
        # Create RMA picking
        action = wizard.action_create_rma_picking()
        
        # Verify picking creation
        picking = self.env['stock.picking'].browse(action['res_id'])
        self.assertEqual(picking.partner_id, self.partner)
        self.assertEqual(len(picking.move_ids), 2)
        
        # Verify moves
        move1 = picking.move_ids.filtered(lambda m: m.product_id == self.product1)
        move2 = picking.move_ids.filtered(lambda m: m.product_id == self.product2)
        
        self.assertEqual(move1.product_uom_qty, 1.0)
        self.assertEqual(move2.product_uom_qty, 2.0)
        self.assertEqual(move1.lot_ids, self.lot1)
        
        # Verify claim linkage
        self.assertIn(picking, self.claim.rma_in_picking_ids)
        self.assertEqual(self.claim.status, 'awaiting_return')
    
    def test_rma_wizard_validation(self):
        """Test that wizard validates required fields"""
        # Test empty lines validation
        wizard = self.env['warranty.rma.receive.wizard'].with_context({
            'default_claim_id': self.claim.id,
            'default_partner_id': self.partner.id,
        }).create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
        })
        
        with self.assertRaises(Exception) as context:
            wizard.action_create_rma_picking()
        self.assertIn('Please add at least one return line', str(context.exception))