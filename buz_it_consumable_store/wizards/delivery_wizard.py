from odoo import api, fields, models, _


class BuzItConsumableDeliverWizard(models.TransientModel):
    _name = 'buz.it.consumable.deliver.wizard'
    _description = 'Deliver Consumable'

    line_id = fields.Many2one(
        'buz.it.consumable.request.line',
        string='รายการ',
        required=True,
        readonly=True,
    )
    consumable_id = fields.Many2one(
        'buz.it.consumable',
        related='line_id.consumable_id',
        string='สินค้า',
        readonly=True,
    )
    unit = fields.Char(
        related='line_id.unit',
        string='หน่วย',
        readonly=True,
    )
    requested_qty = fields.Float(
        related='line_id.requested_qty',
        string='จำนวนที่ขอ',
        readonly=True,
        digits=(16, 0),
    )
    delivered_qty = fields.Float(
        related='line_id.delivered_qty',
        string='จ่ายแล้ว',
        readonly=True,
        digits=(16, 0),
    )
    remaining_qty = fields.Float(
        related='line_id.remaining_qty',
        string='เหลือจ่าย',
        readonly=True,
        digits=(16, 0),
    )
    on_hand_qty = fields.Float(
        related='line_id.consumable_id.on_hand_qty',
        string='ยอดคงเหลือรวม',
        readonly=True,
        digits=(16, 0),
    )
    location_ids = fields.Many2many(
        'buz.it.stock.location',
        compute='_compute_location_ids',
        string='Location ที่มีของ',
    )
    qty = fields.Float(
        string='จำนวนที่จะจ่าย',
        digits=(16, 0),
        required=True,
    )
    location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location ที่จ่าย',
        required=True,
        domain="[('id', 'in', location_ids)]",
    )

    @api.depends('line_id')
    def _compute_location_ids(self):
        for wiz in self:
            wiz.location_ids = (
                wiz.line_id._get_deliverable_locations()
                if wiz.line_id else False
            )

    @api.onchange('line_id')
    def _onchange_line_id(self):
        self.qty = self.line_id.remaining_qty or 0.0

    @api.onchange('qty', 'location_id')
    def _onchange_qty_location(self):
        if not self.line_id:
            return {}
        max_qty = min(self.remaining_qty, self.on_hand_qty)
        if self.location_id:
            quant = self.env['buz.it.stock.quant'].search([
                ('consumable_id', '=', self.consumable_id.id),
                ('location_id', '=', self.location_id.id),
            ], limit=1)
            if quant:
                max_qty = min(max_qty, quant.qty)
        if self.qty > max_qty:
            self.qty = max_qty
            return {
                'warning': {
                    'title': _('ของไม่พอ'),
                    'message': _('จ่ายได้สูงสุด %s %s') % (max_qty, self.unit),
                },
            }
        return {}

    def action_deliver(self):
        self.ensure_one()
        self.line_id._do_deliver(self.qty, self.location_id)
        return self.line_id.request_id.get_formview_action()
