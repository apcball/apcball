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
    rec_date = fields.Date(string='Recorded on', help='Day the movement was really recorded.')
    backdated = fields.Boolean(string='Back-dated', help='Recorded after its document date.')
    has_sys = fields.Boolean(string='Compared with system')
    sys_qty = fields.Float(string='System Qty', digits='Product Unit of Measure',
                           help='Quantity the system FIFO queue holds today.')
    sys_value = fields.Float(string='System Value', digits=(16, 2))
    diff_qty = fields.Float(string='Qty Difference', digits='Product Unit of Measure',
                            help='System minus report (lot rows) or minus ledger (total row).')
    diff_value = fields.Float(string='Value Difference', digits=(16, 2))


class BuzPoLotCheck(models.TransientModel):
    _name = 'buz.po.lot.check'
    _description = 'Tax stock report: differences for accounting to review'
    _order = 'wizard_id, id'

    wizard_id = fields.Many2one('buz.po.lot.wizard', ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Product')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    ledger_qty = fields.Float(digits='Product Unit of Measure')
    ledger_value = fields.Float(digits=(16, 2))
    has_sys = fields.Boolean()
    sys_qty = fields.Float(digits='Product Unit of Measure')
    sys_value = fields.Float(digits=(16, 2))
    lot_qty = fields.Float(digits='Product Unit of Measure')
    lot_value = fields.Float(digits=(16, 2))
    diff_sys_qty = fields.Float(digits='Product Unit of Measure')
    diff_sys_value = fields.Float(digits=(16, 2))
    diff_lot_value = fields.Float(digits=(16, 2))
    backdated_count = fields.Integer()
    short_qty = fields.Float(digits='Product Unit of Measure')
    lc_moved_value = fields.Float(digits=(16, 2))
    note = fields.Char()
