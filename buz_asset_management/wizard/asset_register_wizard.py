# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare, float_is_zero


class BuzAssetRegisterWizard(models.TransientModel):
    _name = 'buz.asset.register.wizard'
    _description = 'สร้างทรัพย์สินจากใบแจ้งหนี้ผู้ขาย'

    move_id = fields.Many2one('account.move', required=True, readonly=True, string='ใบแจ้งหนี้ผู้ขาย')
    company_id = fields.Many2one('res.company', related='move_id.company_id', string='บริษัท')
    line_ids = fields.One2many('buz.asset.register.wizard.line', 'wizard_id', string='รายการ')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move = self.env['account.move'].browse(res.get('move_id') or self.env.context.get('default_move_id'))
        if move:
            Acq = self.env['buz.asset.acquisition']
            commands = []
            for line in move.line_ids.filtered(lambda l: Acq._eligible_amount(l) > 0):
                remaining = Acq._eligible_amount(line) - Acq._allocated_amount(line)
                if float_compare(remaining, 0.0, precision_rounding=move.company_currency_id.rounding) > 0:
                    commands.append(Command.create({
                        'move_line_id': line.id, 'name': line.name or line.product_id.display_name,
                        'amount': remaining}))
            res['line_ids'] = commands
        return res

    def action_create_assets(self):
        self.ensure_one()
        if not self.env.user.has_group('buz_asset_management.group_asset_officer'):
            raise AccessError(_("คุณไม่มีสิทธิ์สร้างทรัพย์สิน"))
        move = self.move_id
        if move.move_type != 'in_invoice' or move.state != 'posted':
            raise UserError(_("ใช้ได้เฉพาะใบแจ้งหนี้ผู้ขายที่ลงบัญชีแล้ว"))
        lines = self.line_ids.filtered(lambda l: not float_is_zero(
            l.amount, precision_rounding=move.company_currency_id.rounding))
        if not lines:
            raise UserError(_("ไม่มีรายการที่จะสร้างทรัพย์สิน"))
        if lines.filtered(lambda l: not l.category_id):
            raise UserError(_("กรุณาเลือกหมวดหมู่ทรัพย์สินให้ครบทุกรายการ"))
        # Serialize concurrent registrations of the same bill lines.
        self.env.cr.execute('SELECT id FROM account_move_line WHERE id IN %s FOR UPDATE',
                            (tuple(lines.move_line_id.ids),))
        Acq = self.env['buz.asset.acquisition']
        planned = defaultdict(float)
        for wl in lines:
            planned[wl.move_line_id] += wl.amount
        for line, amount in planned.items():
            available = Acq._eligible_amount(line) - Acq._allocated_amount(line)
            if float_compare(amount, available, precision_rounding=move.company_currency_id.rounding) > 0:
                raise UserError(_(
                    "จัดสรรรายการ '%(line)s' เกินจำนวนที่เหลือ (%(avail)s)",
                    line=line.display_name, avail=available))
        assets = self.env['buz.asset']
        for wl in lines:
            asset = self.env['buz.asset'].create({
                'name': wl.asset_name or wl.name or move.name,
                'category_id': wl.category_id.id,
                'company_id': move.company_id.id,
                'source_type': 'vendor_bill',
                'source_move_id': move.id,
                'source_ref': move.name,
                'vendor_id': move.partner_id.id,
                'purchase_date': move.invoice_date,
                'gross_cost': wl.amount,
                'useful_life_months': wl.category_id.useful_life_months,
                'depreciation_method': wl.category_id.depreciation_method,
            })
            # sudo: officers have no direct create on allocations; group checked above,
            # constraints (eligibility, overrun, company) still run.
            Acq.sudo().create({'asset_id': asset.id, 'move_line_id': wl.move_line_id.id, 'amount': wl.amount})
            assets |= asset
        return {
            'type': 'ir.actions.act_window', 'res_model': 'buz.asset', 'name': _('ทรัพย์สินที่สร้าง'),
            'view_mode': 'tree,form', 'domain': [('id', 'in', assets.ids)]}


class BuzAssetRegisterWizardLine(models.TransientModel):
    _name = 'buz.asset.register.wizard.line'
    _description = 'รายการสร้างทรัพย์สินจากใบแจ้งหนี้'

    wizard_id = fields.Many2one('buz.asset.register.wizard', required=True, ondelete='cascade')
    move_line_id = fields.Many2one('account.move.line', required=True, string='รายการในใบแจ้งหนี้')
    name = fields.Char(string='รายละเอียด')
    asset_name = fields.Char(string='ชื่อทรัพย์สิน')
    category_id = fields.Many2one('buz.asset.category', string='หมวดหมู่')
    currency_id = fields.Many2one('res.currency', related='wizard_id.company_id.currency_id')
    amount = fields.Monetary(currency_field='currency_id', string='ราคาทุนที่จัดสรร')
