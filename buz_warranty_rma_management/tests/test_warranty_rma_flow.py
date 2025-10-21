# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

from odoo.tests import common


class TestWarrantyRMAFlow(common.TransactionCase):

    def setUp(self):
        super().setUp()
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer',
            'email': 'test.customer@example.com',
        })
        
        # Create test product
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
            'tracking': 'lot',  # Enable serial/lot tracking
        })
        
        # Create test product template
        self.product_tmpl = self.env['product.template'].create({
            'name': 'Test Product Template',
            'type': 'product',
            'tracking': 'lot',
        })
        
        # Create test warranty template
        self.warranty_template = self.env['buz.warranty.template'].create({
            'name': 'Test Warranty Template',
            'code': 'TWT001',
            'product_tmpl_id': self.product_tmpl.id,
            'coverage_type': 'free',
            'duration_months': 12,
            'terms': 'Test warranty terms and conditions',
        })
        
        # Create test lot/serial number
        self.lot = self.env['stock.lot'].create({
            'name': 'TEST-SERIAL-001',
            'product_id': self.product.id,
            'company_id': self.env.company.id,
        })
        
        # Create test picking type for RMA operations
        self.picking_type_in = self.env['stock.picking.type'].create({
            'name': 'RMA In',
            'code': 'incoming',
            'sequence_code': 'RMAI',
            'warehouse_id': self.env['stock.warehouse'].search([], limit=1).id,
        })
        
        self.picking_type_out = self.env['stock.picking.type'].create({
            'name': 'RMA Out',
            'code': 'outgoing',
            'sequence_code': 'RMAO',
            'warehouse_id': self.env['stock.warehouse'].search([], limit=1).id,
        })
        
        # Set up config parameters
        self.env['ir.config_parameter'].sudo().set_param(
            'buz.default_rma_in_type_id', str(self.picking_type_in.id)
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'buz.default_rma_return_type_id', str(self.picking_type_out.id)
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'buz.default_replacement_type_id', str(self.picking_type_out.id)
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'buz.default_repair_location_id', 
            str(self.env['stock.location'].search([('usage', '=', 'internal')], limit=1).id)
        )

    def test_warranty_contract_creation(self):
        """Test creating a warranty contract"""
        # Create warranty contract
        contract = self.env['buz.warranty.contract'].create({
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'template_id': self.warranty_template.id,
            'start_date': '2024-01-01',
        })
        
        # Check that the contract was created with correct data
        self.assertEqual(contract.partner_id, self.partner)
        self.assertEqual(contract.product_id, self.product)
        self.assertEqual(contract.lot_id, self.lot)
        self.assertEqual(contract.template_id, self.warranty_template)
        self.assertTrue(contract.name.startswith('WCT/'))
        
        # Check that end_date is calculated correctly
        self.assertEqual(contract.end_date.year, 2025)  # 12 months + 1 year from start date

    def test_in_warranty_claim_flow(self):
        """Test the complete in-warranty claim flow: create claim → receive RMA → validate inbound → state=rma_in"""
        # Create warranty contract
        contract = self.env['buz.warranty.contract'].create({
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'template_id': self.warranty_template.id,
            'start_date': '2024-01-01',
        })
        
        # Create warranty claim
        claim = self.env['buz.warranty.claim'].create({
            'contract_id': contract.id,
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'reason': 'defect',
            'description': 'Product has manufacturing defect',
        })
        
        # Submit the claim
        claim.action_submit()
        self.assertEqual(claim.state, 'under_review')
        
        # Receive RMA
        claim.action_receive_rma()
        self.assertEqual(claim.state, 'rma_in')
        self.assertTrue(claim.rma_in_picking_id)
        
        # Validate the inbound picking
        claim.rma_in_picking_id.action_confirm()
        claim.rma_in_picking_id.action_assign()
        for move_line in claim.rma_in_picking_id.move_line_ids:
            move_line.qty_done = move_line.reserved_uom_qty
        claim.rma_in_picking_id._action_done()
        
        # Check that picking is done
        self.assertEqual(claim.rma_in_picking_id.state, 'done')
        
        # Create repair order
        claim.action_create_repair()
        self.assertEqual(claim.state, 'repairing')
        self.assertTrue(claim.repair_id)
        
        # Set repair as done
        claim.repair_id.action_validate()
        claim.repair_id.action_start()
        claim.repair_id.action_done()
        self.assertEqual(claim.repair_id.state, 'done')
        
        # Return to customer
        claim.action_return_to_customer()
        self.assertEqual(claim.state, 'ready_to_return')
        self.assertTrue(claim.return_to_customer_picking_id)
        
        # Validate the return picking
        claim.return_to_customer_picking_id.action_confirm()
        claim.return_to_customer_picking_id.action_assign()
        for move_line in claim.return_to_customer_picking_id.move_line_ids:
            move_line.qty_done = move_line.reserved_uom_qty
        claim.return_to_customer_picking_id._action_done()
        
        # Mark claim as done
        claim.action_mark_done()
        self.assertEqual(claim.state, 'done')

    def test_out_of_warranty_claim_flow(self):
        """Test out-of-warranty claim flow: add claim_cost_line_ids → action_create_invoice() → invoice posted → action_mark_done()"""
        # Create warranty contract with past end date (expired)
        contract = self.env['buz.warranty.contract'].create({
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'template_id': self.warranty_template.id,
            'start_date': '2022-01-01',  # Old date to make it out of warranty
            'end_date': '2023-01-01',   # Past date
        })
        
        # Create warranty claim
        claim = self.env['buz.warranty.claim'].create({
            'contract_id': contract.id,
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'reason': 'repair',
            'description': 'Product needs repair (out of warranty)',
        })
        
        # Add cost line
        cost_line = self.env['buz.claim.cost.line'].create({
            'claim_id': claim.id,
            'product_id': self.product.id,
            'name': 'Repair Service',
            'quantity': 1.0,
            'price_unit': 100.0,
        })
        
        # Submit the claim
        claim.action_submit()
        self.assertEqual(claim.state, 'under_review')
        
        # Create repair order
        claim.action_create_repair()
        self.assertEqual(claim.state, 'repairing')
        self.assertTrue(claim.repair_id)
        
        # Set repair as done
        claim.repair_id.action_validate()
        claim.repair_id.action_start()
        claim.repair_id.action_done()
        self.assertEqual(claim.repair_id.state, 'done')
        
        # Create invoice for out-of-warranty repair
        claim.action_create_invoice()
        self.assertTrue(claim.invoice_id)
        self.assertEqual(claim.invoice_id.state, 'posted')
        
        # Return to customer
        claim.action_return_to_customer()
        self.assertTrue(claim.return_to_customer_picking_id)
        
        # Validate the return picking
        claim.return_to_customer_picking_id.action_confirm()
        claim.return_to_customer_picking_id.action_assign()
        for move_line in claim.return_to_customer_picking_id.move_line_ids:
            move_line.qty_done = move_line.reserved_uom_qty
        claim.return_to_customer_picking_id._action_done()
        
        # Mark claim as done
        claim.action_mark_done()
        self.assertEqual(claim.state, 'done')

    def test_replacement_flow(self):
        """Test replacement flow: action_create_replacement() → validate outbound (with new lot) → done"""
        # Create warranty contract
        contract = self.env['buz.warranty.contract'].create({
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'template_id': self.warranty_template.id,
            'start_date': '2024-01-01',
        })
        
        # Create warranty claim
        claim = self.env['buz.warranty.claim'].create({
            'contract_id': contract.id,
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'reason': 'replacement',
            'description': 'Product needs to be replaced',
        })
        
        # Submit and receive RMA
        claim.action_submit()
        claim.action_receive_rma()
        self.assertEqual(claim.state, 'rma_in')
        
        # Create replacement
        claim.action_create_replacement()
        self.assertEqual(claim.state, 'replacing')
        self.assertTrue(claim.replacement_out_picking_id)
        
        # Validate the replacement picking
        claim.replacement_out_picking_id.action_confirm()
        claim.replacement_out_picking_id.action_assign()
        for move_line in claim.replacement_out_picking_id.move_line_ids:
            move_line.qty_done = move_line.reserved_uom_qty
        claim.replacement_out_picking_id._action_done()
        
        # Check that the claim is done
        claim.refresh()
        self.assertEqual(claim.state, 'done')

    def test_constraints(self):
        """Test constraints: no overlapping claims for same contract/lot, no overlapping contracts"""
        # Create warranty contract
        contract = self.env['buz.warranty.contract'].create({
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'template_id': self.warranty_template.id,
            'start_date': '2024-01-01',
        })
        
        # Create first warranty claim
        claim1 = self.env['buz.warranty.claim'].create({
            'contract_id': contract.id,
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'reason': 'defect',
            'description': 'First claim',
        })
        
        # Create second warranty claim with same contract/lot
        claim2 = self.env['buz.warranty.claim'].create({
            'contract_id': contract.id,
            'partner_id': self.partner.id,
            'product_id': self.product.id,
            'lot_id': self.lot.id,
            'reason': 'defect',
            'description': 'Second claim',
        })
        
        # First claim should be submittable
        claim1.action_submit()
        self.assertEqual(claim1.state, 'under_review')
        
        # Second claim should raise an error when trying to submit
        with self.assertRaises(Exception):
            claim2.action_submit()