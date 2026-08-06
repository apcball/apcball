from collections import defaultdict

from odoo import api, fields, models, _


class BuzItConsumable(models.Model):
    _name = 'buz.it.consumable'
    _description = 'IT Consumable Item'
    _order = 'category_id, name'

    name = fields.Char(string='ชื่อ', required=True)
    image_1920 = fields.Image(string='รูปภาพ', max_width=1024, max_height=1024)
    category_id = fields.Many2one(
        'buz.it.consumable.category',
        string='หมวดหมู่',
        ondelete='restrict',
    )
    unit = fields.Char(string='หน่วย', required=True, default='ชิ้น')
    max_per_request = fields.Float(
        string='สูงสุดต่อคำขอ',
        digits=(16, 0),
        default=0.0,
        help='0 = ไม่จำกัด',
    )
    low_stock_threshold = fields.Float(
        string='เกณฑ์แจ้งเตือนใกล้หมด',
        digits=(16, 0),
        default=0.0,
        help='0 = ไม่แจ้งเตือน',
    )
    is_published = fields.Boolean(string='แสดงในหน้าร้าน', default=True)
    active = fields.Boolean(default=True)
    description = fields.Text(string='รายละเอียดเพิ่มเติม')
    company_id = fields.Many2one(
        'res.company',
        string='บริษัท',
        required=True,
        default=lambda self: self.env.company,
        ondelete='restrict',
    )
    quant_ids = fields.One2many(
        'buz.it.stock.quant',
        'consumable_id',
        string='Stock ตาม Location',
        readonly=True,
    )
    on_hand_qty = fields.Float(
        compute='_compute_on_hand_qty',
        store=True,
        string='ยอดคงเหลือ',
        digits=(16, 0),
    )
    low_stock = fields.Boolean(
        compute='_compute_low_stock',
        store=True,
        string='ใกล้หมด',
    )
    @api.depends('quant_ids.qty')
    def _compute_on_hand_qty(self):
        grouped = defaultdict(float)
        quants = self.env['buz.it.stock.quant'].sudo().search([
            ('consumable_id', 'in', self.ids),
        ])
        for quant in quants:
            grouped[quant.consumable_id.id] += quant.qty
        for rec in self:
            rec.on_hand_qty = grouped.get(rec.id, 0.0)

    @api.depends('on_hand_qty', 'low_stock_threshold')
    def _compute_low_stock(self):
        for rec in self:
            rec.low_stock = (
                bool(rec.low_stock_threshold)
                and rec.on_hand_qty <= rec.low_stock_threshold
            )

