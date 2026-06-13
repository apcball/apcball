from odoo import fields, models


class BuzDispatchDocumentLine(models.Model):
    _name = 'buz.dispatch.document.line'
    _description = 'Dispatch Document Line'
    _order = 'id'

    dispatch_id = fields.Many2one(
        'buz.dispatch.document',
        string='Dispatch',
        required=True,
        ondelete='cascade',
    )

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
    )

    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
    )

    ordered_qty = fields.Float(
        string='Ordered Qty',
        digits='Product Unit of Measure',
        default=0.0,
    )

    dispatch_qty = fields.Float(
        string='Dispatch Qty',
        digits='Product Unit of Measure',
        required=True,
        default=0.0,
    )

    sale_line_id = fields.Many2one(
        'sale.order.line',
        string='Sale Order Line',
    )

    move_line_id = fields.Many2one(
        'stock.move.line',
        string='Stock Move Line',
    )

    remark = fields.Char(string='Remark')
