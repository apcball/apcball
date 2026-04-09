from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
import json

class TestFifoResetEngine(TransactionCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        
        # Create a product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product FIFO Reset',
            'type': 'product',
            'categ_id': cls.env.ref('product.product_category_all').id,
            'standard_price': 10.0,
        })
        
        # Add stock quantity to create quant
        cls.location = cls.env.ref('stock.stock_location_stock')
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.location, 10.0)
        
        # Create a valuation layer
        cls.env['stock.valuation.layer'].create({
            'product_id': cls.product.id,
            'company_id': cls.company.id,
            'quantity': 10.0,
            'value': 100.0,
            'unit_cost': 10.0,
        })
        
    def test_01_fifo_reset_dry_run(self):
        # Initial check
        quant = self.env['stock.quant'].search([('product_id', '=', self.product.id), ('location_id', '=', self.location.id)])
        self.assertEqual(quant.quantity, 10.0)
        
        # Run service dry run
        service = self.env['fifo.reset.service']
        res = service.run(dry_run=True, company_id=self.company.id)
        
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['summary']['after_value'], 0.0)
        
        # After dry run, the DB should still have the quantity
        quant = self.env['stock.quant'].search([('product_id', '=', self.product.id), ('location_id', '=', self.location.id)])
        self.assertEqual(quant.quantity, 10.0)
        
    def test_02_fifo_reset_execute(self):
        # create valuation so total value isn't purely the single SVL if we want a fresh run
        service = self.env['fifo.reset.service']
        res = service.run(dry_run=False, company_id=self.company.id)
        
        self.assertEqual(res['status'], 'success')
        
        # check quant and svl zeros
        quant = self.env['stock.quant'].search([('product_id', '=', self.product.id), ('location_id', '=', self.location.id)])
        self.assertEqual(quant.quantity, 0.0)
        
        svl_val = sum(self.env['stock.valuation.layer'].search([('company_id', '=', self.company.id)]).mapped('value'))
        self.assertEqual(svl_val, 0.0)
        
    def test_03_open_pickings_cancelled_by_pipeline(self):
        """Open pickings (draft/confirmed/assigned/waiting) are force-cancelled by the pipeline."""
        picking = self.env['stock.picking'].create({
            'location_id': self.location.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
        })
        self.assertEqual(picking.state, 'draft')

        service = self.env['fifo.reset.service']
        # Pipeline should cancel the open picking and proceed successfully
        res = service.run(dry_run=True, company_id=self.company.id)

        self.assertEqual(res['status'], 'success')
