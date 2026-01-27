from odoo.tests import common
from odoo.exceptions import ValidationError


class TestStockCurrentTransfer(common.TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Create test data
        self.warehouse = self.env['stock.warehouse'].create({
            'name': 'Test Warehouse',
            'code': 'TW'
        })
        
        self.location_src = self.warehouse.lot_stock_id
        self.location_dest = self.env['stock.location'].create({
            'name': 'Test Destination Location',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id
        })
        
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'uom_po_id': self.env.ref('uom.product_uom_unit').id
        })
        
        # Create stock quant
        self.env['stock.quant']._update_available_quantity(
            self.product, self.location_src, 100
        )

    def test_transfer_wizard_creation(self):
        """Test transfer wizard creation with selected products"""
        product_data = [{
            'productId': self.product.id,
            'locationId': self.location_src.id,
            'quantity': 50,
            'uomId': self.product.uom_id.id,
            'productName': self.product.name,
            'locationName': self.location_src.name
        }]
        
        wizard = self.env['stock.current.transfer.wizard'].with_context(
            default_selected_products=product_data
        ).create({})
        
        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids[0].product_id, self.product)
        self.assertEqual(wizard.line_ids[0].quantity_to_transfer, 50)
        self.assertEqual(wizard.line_ids[0].available_quantity, 100)

    def test_transfer_wizard_validation(self):
        """Test transfer wizard validation"""
        product_data = [{
            'productId': self.product.id,
            'locationId': self.location_src.id,
            'quantity': 150,  # More than available
            'uomId': self.product.uom_id.id,
            'productName': self.product.name,
            'locationName': self.location_src.name
        }]
        
        wizard = self.env['stock.current.transfer.wizard'].with_context(
            default_selected_products=product_data
        ).create({})
        
        # Should raise validation error when trying to transfer more than available
        with self.assertRaises(ValidationError):
            wizard.action_create_transfer()

    def test_transfer_creation(self):
        """Test actual transfer creation"""
        product_data = [{
            'productId': self.product.id,
            'locationId': self.location_src.id,
            'quantity': 50,
            'uomId': self.product.uom_id.id,
            'productName': self.product.name,
            'locationName': self.location_src.name
        }]
        
        wizard = self.env['stock.current.transfer.wizard'].with_context(
            default_selected_products=product_data
        ).create({
            'destination_location_id': self.location_dest.id,
            'immediate_transfer': True
        })
        
        # Create transfer
        action = wizard.action_create_transfer()
        
        # Check if picking was created
        self.assertEqual(action['res_model'], 'stock.picking')
        picking = self.env['stock.picking'].browse(action['res_id'])
        self.assertEqual(picking.state, 'done')  # Should be validated immediately
        self.assertEqual(picking.location_id, self.location_src)
        self.assertEqual(picking.location_dest_id, self.location_dest)
        
        # Check if stock move was created
        self.assertEqual(len(picking.move_ids), 1)
        move = picking.move_ids[0]
        self.assertEqual(move.product_id, self.product)
        self.assertEqual(move.product_uom_qty, 50)
        self.assertEqual(move.state, 'done')

    def test_single_product_transfer_action(self):
        """Test single product transfer action from stock report"""
        # Create stock report record
        stock_report = self.env['stock.current.report'].search([
            ('product_id', '=', self.product.id),
            ('location_id', '=', self.location_src.id)
        ], limit=1)
        
        if not stock_report:
            # Create a mock record for testing
            stock_report = self.env['stock.current.report'].new({
                'product_id': self.product.id,
                'location_id': self.location_src.id,
                'quantity': 100,
                'uom_id': self.product.uom_id.id
            })
        
        # Test action_transfer_single_product
        action = stock_report.action_transfer_single_product()
        
        self.assertEqual(action['res_model'], 'stock.current.transfer.wizard')
        self.assertEqual(action['target'], 'new')
        self.assertIn('default_selected_products', action['context'])
        
        selected_products = action['context']['default_selected_products']
        self.assertEqual(len(selected_products), 1)
        self.assertEqual(selected_products[0]['productId'], self.product.id)
        self.assertEqual(selected_products[0]['locationId'], self.location_src.id)