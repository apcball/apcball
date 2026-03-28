from odoo import models, fields


class StockUnreserveLog(models.Model):
    _name = 'stock.unreserve.log'
    _description = 'Stock Unreserve Audit Log'
    _order = 'datetime desc'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    datetime = fields.Datetime(
        string='Date / Time',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Transfer',
        readonly=True,
        ondelete='set null',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        readonly=True,
        ondelete='set null',
    )
    qty = fields.Float(
        string='Qty Unreserved',
        digits='Product Unit of Measure',
        readonly=True,
    )
    reason = fields.Char(
        string='Reason',
        readonly=True,
    )
    type = fields.Selection(
        selection=[
            ('picking', 'Picking'),
            ('force', 'Force'),
            ('bulk_picking', 'Bulk – Picking'),
            ('bulk_product', 'Bulk – Product'),
            ('bulk_all', 'Bulk – All'),
        ],
        string='Type',
        required=True,
        readonly=True,
    )
