from odoo import fields, models


class BuzPoLotLine(models.TransientModel):
    _name = 'buz.po.lot.line'
    _description = 'Tax stock report line'
    _order = 'wizard_id, product_id, seq'

    wizard_id = fields.Many2one('buz.po.lot.wizard', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product')
    model_code = fields.Char(string='Model')
    seq = fields.Integer()
    line_type = fields.Selection([
        ('opening', 'Opening'),
        ('move', 'Movement'),
        ('lotbal', 'Lot balance'),
        ('lot', 'Ending lot'),
        ('lotlc', 'Landed cost on lot'),
        ('adjust', 'Value adjustment'),
        ('total', 'Total'),
    ], string='Type')
    date = fields.Date()
    doc_ref = fields.Char(string='Document')
    wh_date = fields.Date(string='Entered warehouse',
                          help='Day the lot entered this warehouse (FIFO queue order).')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    in_qty = fields.Float(digits='Product Unit of Measure')
    in_cost = fields.Float(string='In @', digits=(16, 4))
    in_value = fields.Float(string='In Value', digits=(16, 2))
    in_allin = fields.Float(string='All-in @', digits=(16, 4),
                            help='(layer value + all landed cost booked on it) / qty, receipt rows only.')
    out_qty = fields.Float(digits='Product Unit of Measure')
    out_cost = fields.Float(string='Out @', digits=(16, 4))
    out_value = fields.Float(string='Out Value', digits=(16, 2))
    bal_qty = fields.Float(string='Balance Qty', digits='Product Unit of Measure')
    bal_cost = fields.Float(string='Balance @', digits=(16, 4))
    bal_value = fields.Float(string='Balance Value', digits=(16, 2))
