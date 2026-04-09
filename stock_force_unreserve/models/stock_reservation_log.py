from odoo import models, fields

class StockReservationLog(models.Model):
    _name = 'stock.reservation.log'
    _description = 'Stock Reservation Audit Log'
    _order = 'create_date desc'

    product_id = fields.Many2one('product.product', string='Product', required=True)
    source_picking_id = fields.Many2one('stock.picking', string='Stolen From', required=True)
    target_picking_id = fields.Many2one('stock.picking', string='Assigned To', required=True)
    qty_moved = fields.Float(string='Quantity Moved', required=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
