# -*- coding: utf-8 -*-
"""
Payment Voucher Wizard

TransientModel wizard for filtering and exporting payment vouchers to XLSX.
"""
from odoo import fields, models, _
from odoo.exceptions import UserError


class PaymentVoucherWizard(models.TransientModel):
    _name = 'buz.payment.voucher.wizard'
    _description = 'Payment Voucher Wizard'

    date_from = fields.Date(string='Date From', help='Start date for payment filter')
    date_to = fields.Date(string='Date To', help='End date for payment filter')
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        domain=['|', ('parent_id', '=', False), ('is_company', '=', True)],
        help='Filter by customer or vendor',
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        domain=[('type', 'in', ('bank', 'cash', 'general'))],
        help='Filter by payment journal',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        help='Filter by company',
    )
    payment_type = fields.Selection(
        selection=[
            ('inbound', 'Customer Payment'),
            ('outbound', 'Vendor Payment'),
            ('transfer', 'Internal Transfer'),
        ],
        string='Payment Type',
        help='Filter by payment type',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('sent', 'Sent'),
            ('reconciled', 'Reconciled'),
        ],
        string='State',
        help='Filter by payment state',
    )
    sort_by = fields.Selection(
        selection=[
            ('payment_date', 'Payment Date'),
            ('payment_name', 'Payment Number'),
            ('partner_id', 'Partner'),
            ('journal_id', 'Journal'),
        ],
        string='Sort By',
        default='payment_date',
        required=True,
        help='Sort payments by selected field',
    )

    def _build_domain(self):
        domain = [('company_id', '=', self.company_id.id)]
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        if self.journal_id:
            domain.append(('journal_id', '=', self.journal_id.id))
        if self.payment_type:
            domain.append(('payment_type', '=', self.payment_type))
        if self.state:
            domain.append(('state', '=', self.state))
        return domain

    def _get_payment_sort_order(self):
        sort_map = {
            'payment_date': 'date ASC, name ASC, id ASC',
            'payment_name': 'name ASC, date ASC, id ASC',
            'partner_id': 'partner_id ASC, date ASC, name ASC, id ASC',
            'journal_id': 'journal_id ASC, date ASC, name ASC, id ASC',
        }
        return sort_map.get(self.sort_by, 'date ASC, name ASC, id ASC')

    def _get_payments(self):
        self.ensure_one()
        return self.env['account.payment'].search(
            self._build_domain(),
            order=self._get_payment_sort_order(),
        )

    def action_print_xlsx(self):
        self.ensure_one()
        payments = self._get_payments()
        if not payments:
            raise UserError(_('No payments found for the selected criteria.'))
        return self.env.ref(
            'buz_payment_voucher_report.action_report_payment_voucher_xlsx'
        ).report_action(payments, data={'sort_by': self.sort_by})
