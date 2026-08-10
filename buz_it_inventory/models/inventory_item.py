from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError

OPEN_REQUEST_STATES = ('submitted', 'partially_issued')


class BuzItInventoryItem(models.Model):
    _name = 'buz.it.inventory.item'
    _description = 'IT Inventory Item'
    _order = 'category_id, name'

    name = fields.Char(string='ชื่อ', required=True)
    image_1920 = fields.Image(string='รูปภาพ', max_width=1024, max_height=1024)
    category_id = fields.Many2one(
        'buz.it.inventory.item.category',
        string='หมวดหมู่',
        ondelete='restrict',
    )
    item_type = fields.Selection([
        ('consumable', 'Consumable'),
        ('non_serialized_equipment', 'Non-Serialized Equipment'),
    ], string='Item Type', required=True, default='consumable')
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
        'inventory_item_id',
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
    issue_request_line_ids = fields.One2many(
        'buz.it.issue.request.line',
        'item_id',
        string='Issue Request Lines',
    )
    pending_qty = fields.Float(
        compute='_compute_pending_qty',
        store=True,
        string='ค้างส่งมอบ',
        digits=(16, 0),
        help='ยอดที่ถูกขอไว้แต่ยังไม่จ่าย (คำขอยังไม่เสร็จ)',
    )
    available_qty = fields.Float(
        compute='_compute_available_qty',
        store=True,
        string='พร้อมให้เบิก',
        digits=(16, 0),
        help='ยอดคงเหลือจริงของสินค้า (การยื่นคำขอยังไม่จอง Stock)',
    )
    store_status = fields.Selection([
        ('ready', 'พร้อมเบิก'),
        ('low', 'ไม่พอ'),
        ('out', 'หมด'),
    ], compute='_compute_store_status', string='สถานะหน้าร้าน')

    @api.depends('quant_ids.qty')
    def _compute_on_hand_qty(self):
        grouped = defaultdict(float)
        quants = self.env['buz.it.stock.quant'].sudo().search([
            ('inventory_item_id', 'in', self.ids),
        ])
        for quant in quants:
            grouped[quant.inventory_item_id.id] += quant.qty
        for rec in self:
            rec.on_hand_qty = grouped.get(rec.id, 0.0)

    @api.depends('on_hand_qty', 'low_stock_threshold')
    def _compute_low_stock(self):
        for rec in self:
            rec.low_stock = (
                bool(rec.low_stock_threshold)
                and rec.on_hand_qty <= rec.low_stock_threshold
            )

    @api.depends(
        'issue_request_line_ids.remaining_qty',
        'issue_request_line_ids.request_id.state',
    )
    def _compute_pending_qty(self):
        grouped = defaultdict(float)
        lines = self.env['buz.it.issue.request.line'].sudo().search([
            ('item_id', 'in', self.ids),
            ('request_id.state', 'in', list(OPEN_REQUEST_STATES)),
        ])
        for line in lines:
            grouped[line.item_id.id] += line.remaining_qty
        for rec in self:
            rec.pending_qty = grouped.get(rec.id, 0.0)

    @api.depends('on_hand_qty')
    def _compute_available_qty(self):
        for rec in self:
            rec.available_qty = rec.on_hand_qty

    @api.depends('available_qty', 'low_stock_threshold')
    def _compute_store_status(self):
        for rec in self:
            if rec.available_qty <= 0:
                rec.store_status = 'out'
            elif (
                rec.low_stock_threshold
                and rec.available_qty <= rec.low_stock_threshold
            ):
                rec.store_status = 'low'
            else:
                rec.store_status = 'ready'

    def action_request_item(self):
        """Create a Draft issue request for this item from the Store card."""
        self.ensure_one()
        if not self.is_published:
            raise UserError(_('This item is not available in the Store.'))
        if self.available_qty <= 0:
            raise UserError(_('This item is out of stock.'))
        request = self.env['buz.it.issue.request'].create({
            'line_ids': [fields.Command.create({
                'item_id': self.id,
                'requested_qty': 1.0,
            })],
        })
        return {
            'name': _('Issue Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.it.issue.request',
            'res_id': request.id,
            'view_mode': 'form',
            'views': [(self.env.ref('buz_it_inventory.view_issue_request_form').id, 'form')],
            'target': 'current',
        }
