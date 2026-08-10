from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class BuzItStockAdjustWizard(models.TransientModel):
    _name = 'buz.it.stock.adjust.wizard'
    _description = 'Adjust IT Stock'

    inventory_item_id = fields.Many2one(
        'buz.it.inventory.item',
        string='สินค้า',
        required=True,
    )
    location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location',
        required=True,
        domain="[('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        'res.company',
        related='inventory_item_id.company_id',
        string='บริษัท',
    )
    current_qty = fields.Float(
        compute='_compute_current_qty',
        string='ยอดปัจจุบัน',
        digits=(16, 0),
        readonly=True,
    )
    new_qty = fields.Float(
        string='ยอดใหม่',
        digits=(16, 0),
        required=True,
    )

    @api.depends('inventory_item_id', 'location_id')
    def _compute_current_qty(self):
        for wiz in self:
            quant = self.env['buz.it.stock.quant'].sudo().search([
                ('inventory_item_id', '=', wiz.inventory_item_id.id),
                ('location_id', '=', wiz.location_id.id),
            ], limit=1)
            wiz.current_qty = quant.qty if quant else 0.0

    @api.onchange('inventory_item_id')
    def _onchange_inventory_item_id(self):
        self.location_id = False
        self.new_qty = 0.0

    @api.onchange('location_id')
    def _onchange_location_id(self):
        self.new_qty = self.current_qty or 0.0

    def action_adjust(self):
        self.ensure_one()
        if not self.env.user.has_group(
            'buz_it_helpdesk.group_it_helpdesk_manager'
        ):
            raise UserError(_(
                'Only a Helpdesk Manager can adjust stock.'
            ))
        if self.new_qty < 0:
            raise UserError(_('ยอดใหม่ต้องไม่ติดลบ'))
        if self.location_id.company_id != self.inventory_item_id.company_id:
            raise UserError(_('Location และสินค้าต้องอยู่บริษัทเดียวกัน'))
        diff = self.new_qty - self.current_qty
        if float_is_zero(diff, precision_digits=0):
            return {'type': 'ir.actions.act_window_close'}
        self.env.cr.execute(
            'SELECT id FROM buz_it_stock_quant '
            'WHERE inventory_item_id = %s AND location_id = %s FOR UPDATE',
            (self.inventory_item_id.id, self.location_id.id),
        )
        quant = self.env['buz.it.stock.quant'].sudo().search([
            ('inventory_item_id', '=', self.inventory_item_id.id),
            ('location_id', '=', self.location_id.id),
        ], limit=1)
        if not quant:
            quant = self.env['buz.it.stock.quant'].with_context(
                buz_quant_write=True,
            ).sudo().create({
                'inventory_item_id': self.inventory_item_id.id,
                'location_id': self.location_id.id,
                'qty': 0.0,
            })
        quant.with_context(buz_quant_write=True).sudo().write({
            'qty': self.new_qty,
        })
        self.env['buz.it.stock.history'].sudo().create({
            'move_type': 'adjust',
            'inventory_item_id': self.inventory_item_id.id,
            'location_id': self.location_id.id,
            'qty': diff,
            'move_date': fields.Date.context_today(self),
            'reference': _('ปรับยอด'),
            'note': _('ปรับจาก %s เป็น %s') % (self.current_qty, self.new_qty),
        })
        return {'type': 'ir.actions.act_window_close'}

