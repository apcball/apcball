# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .ap_dashboard import clear_cache


class ApDashboardLoanManual(models.Model):
    """Manual loan figures of a month, entered by users while the ledger is incomplete.

    A row replaces the ledger-derived drawn / repaid / outstanding of its account for
    that month on the Payment Dashboard loan card (company currency)."""
    _name = 'biz.ap.dashboard.loan.manual'
    _description = 'Dashboard manual loan entry'
    _order = 'year desc, month desc, account_id'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    year = fields.Integer(required=True, default=lambda self: fields.Date.context_today(self).year)
    month = fields.Selection(
        [(str(i), str(i)) for i in range(1, 13)], required=True,
        default=lambda self: str(fields.Date.context_today(self).month))
    account_id = fields.Many2one(
        'account.account', string='บัญชีเงินกู้', required=True,
        domain="[('id', 'in', allowed_account_ids)]")
    allowed_account_ids = fields.Many2many(
        'account.account', compute='_compute_allowed_account_ids')
    drawn = fields.Monetary('เบิกเงินกู้ในเดือน', currency_field='currency_id')
    repaid = fields.Monetary('ชำระคืนเงินต้น', currency_field='currency_id')
    outstanding = fields.Monetary('คงค้างสิ้นเดือน', currency_field='currency_id')
    note = fields.Char('หมายเหตุ')

    _sql_constraints = [
        ('uniq_company_period_account', 'unique(company_id, year, month, account_id)',
         'มีข้อมูลของบัญชีนี้ในเดือนนี้อยู่แล้ว'),
    ]

    @api.depends('company_id')
    def _compute_allowed_account_ids(self):
        for rec in self:
            # company_id is not always sent by the list view onchange (single company)
            company = rec.company_id or self.env.company
            rec.allowed_account_ids = company.apd_loan_account_ids

    @api.constrains('account_id', 'company_id')
    def _check_account_configured(self):
        for rec in self:
            if rec.account_id not in rec.company_id.apd_loan_account_ids:
                raise ValidationError(_('บัญชี %s ไม่ได้ตั้งเป็นบัญชีเงินกู้ใน Settings', rec.account_id.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        clear_cache()
        return super().create(vals_list)

    def write(self, vals):
        clear_cache()
        return super().write(vals)

    def unlink(self):
        clear_cache()
        return super().unlink()
