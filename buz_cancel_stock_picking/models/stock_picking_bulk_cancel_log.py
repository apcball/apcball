from odoo import models, fields

class StockPickingBulkCancelLog(models.Model):
    _name = 'stock.picking.bulk.cancel.log'
    _description = 'Bulk Cancel Stock Picking Log'
    _order = 'create_date desc'

    picking_id = fields.Many2one('stock.picking', string='Picking', ondelete='set null')
    picking_name = fields.Char(string='Picking Reference', required=True)
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Status', required=True)
    message = fields.Text(string='Message')
