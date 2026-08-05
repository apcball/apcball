from odoo import fields, models


class BuzItStockHistory(models.Model):
    _name = 'buz.it.stock.history'
    _description = 'IT Stock History'
    _order = 'move_date desc, create_date desc, id desc'

    move_type = fields.Selection([
        ('in', 'รับเข้า'),
        ('out', 'จ่ายออก'),
        ('adjust', 'ปรับยอด'),
    ], string='Type', required=True)
    consumable_id = fields.Many2one(
        'buz.it.consumable',
        string='Item',
        required=True,
        ondelete='restrict',
        index=True,
    )
    location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location',
        required=True,
        ondelete='restrict',
    )
    qty = fields.Float(
        string='จำนวน',
        digits=(16, 0),
        required=True,
        help='การเปลี่ยนแปลงยอด (+ รับเข้า, - จ่ายออก, +/- ปรับยอด)',
    )
    move_date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    reference = fields.Char(string='Reference')
    note = fields.Text()
    request_line_id = fields.Many2one(
        'buz.it.consumable.request.line',
        string='Request Line',
        ondelete='set null',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='location_id.company_id',
        store=True,
        string='Company',
        index=True,
    )
