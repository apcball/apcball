# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class VatUndueUseWizard(models.TransientModel):
    _name = 'vat.undue.use.wizard'
    _description = 'VAT Undue Use Wizard'

    undue_line_ids = fields.Many2many(
        'tax.undue.line',
        string='Tax Undue Lines',
        required=True,
        readonly=True
    )
    accounting_date = fields.Date(
        string='Accounting Date',
        required=True,
        default=fields.Date.context_today,
        help='วันที่ที่ต้องการลงบัญชีในรายการโอน VAT Undue ไปเป็น Input VAT'
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        currency_field='currency_id',
        store=False
    )
    line_count = fields.Integer(
        string='Number of Lines',
        compute='_compute_line_count',
        store=False
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True
    )

    @api.depends('undue_line_ids')
    def _compute_total_amount(self):
        for wizard in self:
            wizard.total_amount = sum(wizard.undue_line_ids.mapped('remaining_tax_amount'))

    @api.depends('undue_line_ids')
    def _compute_line_count(self):
        for wizard in self:
            wizard.line_count = len(wizard.undue_line_ids)

    def action_confirm_use_vat(self):
        """ยืนยันการใช้ VAT และสร้าง Journal Entries"""
        self.ensure_one()
        
        if not self.undue_line_ids:
            raise UserError(_("No tax undue lines selected."))
        
        # เรียกใช้ method เดิมจาก tax.undue.line แต่ส่ง accounting_date ไปด้วย
        moves = self.undue_line_ids.with_context(
            accounting_date=self.accounting_date
        )._process_use_vat()
        
        # แสดงผลลัพธ์
        return {
            'type': 'ir.actions.act_window',
            'name': _('VAT Clearing Entries'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', moves.ids)],
            'context': {'create': False},
        }
