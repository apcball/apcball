from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    warranty_rma_in_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='RMA IN Picking Type',
        config_parameter='buz_warranty_management.warranty_rma_in_picking_type_id',
        domain="[('code', '=', 'incoming')]",
        help='Picking type for customer returns (Customer → Repair Location)'
    )
    warranty_repair_location_id = fields.Many2one(
        'stock.location',
        string='Repair Location',
        config_parameter='buz_warranty_management.warranty_repair_location_id',
        domain="[('usage', '=', 'internal')]",
        help='Internal location for diagnosis and repair'
    )
    warranty_replacement_out_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Replacement OUT Picking Type',
        config_parameter='buz_warranty_management.warranty_replacement_out_picking_type_id',
        domain="[('code', '=', 'outgoing')]",
        help='Picking type for replacement delivery (Repair Location → Customer)'
    )
    warranty_scrap_location_id = fields.Many2one(
        'stock.location',
        string='Scrap Location',
        config_parameter='buz_warranty_management.warranty_scrap_location_id',
        domain="[('scrap_location', '=', True)]",
        help='Location for defective/scrapped items'
    )
    warranty_expense_account_id = fields.Many2one(
        'account.account',
        string='Warranty Expense Account',
        config_parameter='buz_warranty_management.warranty_expense_account_id',
        domain="[('account_type', '=', 'expense')]",
        help='Account for under-warranty replacement costs'
    )
    warranty_default_service_product_id = fields.Many2one(
        'product.product',
        string='Default Service Product',
        config_parameter='buz_warranty_management.warranty_default_service_product_id',
        domain="[('type', '=', 'service')]",
        help='Default service product for out-of-warranty repairs'
    )
