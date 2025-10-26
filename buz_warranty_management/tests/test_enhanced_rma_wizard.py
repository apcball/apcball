from odoo.tests import TransactionCase
from odoo.exceptions import UserError


class TestEnhancedRMAWizard(TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer',
        })
        
        # Create test product
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
            'tracking': 'lot',
        })
        
        # Create test lot
        self.lot = self.env['stock.lot'].create({
            'name': 'TEST-LOT-001',
            'product_id': self.product.id,
            'company_id': self.env.company.id,
        })
        
        # Create warranty card
        self.warranty_card = self.env['warranty.card'].create({
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'start_date': '2024-01-01',
            'state': 'active',
        })
        
        # Create warranty claim
        self.claim = self.env['warranty.claim'].create({
            'warranty_card_id': self.warranty_card.id,
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'claim_type': 'repair',
            'description': 'Test claim description',
        })
        
        # Configure warranty settings
        self.env['ir.config_parameter'].sudo().set_param(
            'buz_warranty_management.warranty_rma_in_picking_type_id',
            self.env.ref('stock.picking_type_in').id
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'buz_warranty_management.warranty_repair_location_id',
            self.env.ref('stock.stock_location_stock').id
        )
    
    def test_auto_populate_main_product(self):
        """Test automatic population of main product"""
        # Open wizard
        wizard = self.env['warranty.rma.receive.wizard'].with_context(
            default_claim_id=self.claim.id
        ).create({})
        
        # Verify auto-population
        self.assertEqual(len(wizard.line_ids), 1, "Should have one auto-populated line")
        self.assertEqual(wizard.line_ids.product_id, self.product, "Should auto-populate main product")
        self.assertEqual(wizard.line_ids.lot_id, self.lot, "Should auto-populate lot number")
        self.assertEqual(wizard.line_ids.qty, 1.0, "Should default to quantity 1")
        self.assertTrue(wizard.line_ids.is_auto_populated, "Should mark as auto-populated")
        self.assertEqual(wizard.line_ids.reason, 'Main product from warranty claim', "Should set default reason")
        self.assertFalse(wizard.main_product_already_rma, "Main product should not be in existing RMA")
    
    def test_existing_rma_handling(self):
        """Test handling when main product is already in existing RMA"""
        # Create an RMA picking first
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner.id,
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.partner.property_stock_customer.id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            'origin': self.claim.name,
        })
        
        # Add move for the main product
        self.env['stock.move'].create({
            'name': f'RMA: {self.product.name}',
            'product_id': self.product.id,
            'product_uom_qty': 1.0,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.partner.property_stock_customer.id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
        })
        
        # Link to claim
        self.claim.write({'rma_in_picking_ids': [(4, picking.id)]})
        
        # Open wizard
        wizard = self.env['warranty.rma.receive.wizard'].with_context(
            default_claim_id=self.claim.id
        ).create({})
        
        # Verify no auto-population
        self.assertEqual(len(wizard.line_ids), 0, "Should not auto-populate when product already in RMA")
        self.assertTrue(wizard.main_product_already_rma, "Should detect main product already in RMA")
    
    def test_manual_product_addition(self):
        """Test manual addition of products"""
        # Create additional product
        additional_product = self.env['product.product'].create({
            'name': 'Additional Product',
            'type': 'product',
        })
        
        # Open wizard
        wizard = self.env['warranty.rma.receive.wizard'].with_context(
            default_claim_id=self.claim.id
        ).create({})
        
        # Add manual line
        wizard.write({
            'line_ids': [(0, 0, {
                'product_id': additional_product.id,
                'qty': 2.0,
                'reason': 'Manual addition test',
            })]
        })
        
        # Verify both lines exist
        self.assertEqual(len(wizard.line_ids), 2, "Should have both auto-populated and manual lines")
        
        # Check auto-populated line
        auto_line = wizard.line_ids.filtered('is_auto_populated')
        self.assertEqual(len(auto_line), 1, "Should have one auto-populated line")
        self.assertEqual(auto_line.product_id, self.product, "Auto line should be main product")
        
        # Check manual line
        manual_line = wizard.line_ids.filtered(lambda l: not l.is_auto_populated)
        self.assertEqual(len(manual_line), 1, "Should have one manual line")
        self.assertEqual(manual_line.product_id, additional_product, "Manual line should be additional product")
        self.assertEqual(manual_line.qty, 2.0, "Manual line should have correct quantity")
    
    def test_create_rma_picking_with_auto_populated_product(self):
        """Test creating RMA picking with auto-populated product"""
        # Open wizard
        wizard = self.env['warranty.rma.receive.wizard'].with_context(
            default_claim_id=self.claim.id
        ).create({})
        
        # Create RMA picking
        result = wizard.action_create_rma_picking()
        
        # Verify picking was created
        self.assertTrue(result.get('res_id'), "Should return picking ID")
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.partner_id, self.partner, "Picking should have correct partner")
        self.assertEqual(picking.origin, self.claim.name, "Picking should have claim as origin")
        
        # Verify move was created
        self.assertEqual(len(picking.move_ids), 1, "Should have one move")
        move = picking.move_ids[0]
        self.assertEqual(move.product_id, self.product, "Move should be for main product")
        self.assertEqual(move.product_uom_qty, 1.0, "Move should have correct quantity")
        
        # Verify claim was updated
        self.assertIn(picking, self.claim.rma_in_picking_ids, "Picking should be linked to claim")
        self.assertEqual(self.claim.status, 'awaiting_return', "Claim status should be updated")
    
    def test_claim_without_product(self):
        """Test wizard behavior with claim without main product"""
        # Create claim without product
        claim_no_product = self.env['warranty.claim'].create({
            'partner_id': self.partner.id,
            'claim_type': 'repair',
            'description': 'Test claim without product',
        })
        
        # Open wizard
        wizard = self.env['warranty.rma.receive.wizard'].with_context(
            default_claim_id=claim_no_product.id
        ).create({})
        
        # Verify no auto-population
        self.assertEqual(len(wizard.line_ids), 0, "Should not auto-populate when claim has no product")
        self.assertFalse(wizard.main_product_already_rma, "Should not flag as existing RMA")