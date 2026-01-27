from odoo import models, fields

class ImportPricelistPreview(models.TransientModel):
    _name = 'import.pricelist.preview'
    _description = 'Import Pricelist Preview'
    
    wizard_id = fields.Many2one('import.pricelist.excel', string='Wizard', ondelete='cascade')
    
    product_xml_id = fields.Char('Product Code') # Or internal ref
    product_name = fields.Char('Product Name')
    product_id = fields.Many2one('product.product', string='Product')
    
    old_price = fields.Float('Old Price')
    new_price = fields.Float('New Price')
    
    old_installation_price = fields.Float('Old Install. Price')
    new_installation_price = fields.Float('New Install. Price')
    
    min_qty = fields.Float('Min Qty')
    
    action = fields.Selection([
        ('create', 'Create'),
        ('update', 'Update'),
        ('skip', 'Skip'),
        ('error', 'Error') # For displaying errors in preview
    ], string='Action')
    
    status = fields.Selection([
        ('ok', 'OK'),
        ('warning', 'Warning'),
        ('error', 'Error')
    ], string='Status')
    
    error_message = fields.Char('Error Message')
    
    # Internal fields to carry over data for apply
    rule_id = fields.Many2one('product.pricelist.item', 'Existing Rule')
    row_data = fields.Text('Row Data JSON') # Store full row data if needed
