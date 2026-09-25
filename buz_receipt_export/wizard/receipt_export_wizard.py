# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ReceiptExportWizard(models.TransientModel):
    """Filters and exports accounting receipt voucher details."""

    _name = 'buz.receipt.export.wizard'
    _description = 'Receipt Voucher Export Wizard'

    date_type = fields.Selection([
        ('voucher_date', 'Voucher Date'),
        ('receipt_date', 'Receipt Date'),
        ('invoice_date', 'Invoice Date'),
    ], string='Date Type', required=True)
    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)
    status = fields.Selection([
        ('all', 'All'), ('draft', 'Draft'), ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], string='Receipt Status', required=True, default='posted')
    amount_basis = fields.Selection([
        ('invoice_total', 'Invoice Total'),
        ('amount_to_collect', 'Amount to Collect'),
        ('paid_to_date', 'Paid to Date'),
        ('residual', 'Residual Amount'),
    ], string='Amount Basis', required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, readonly=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one('res.partner', string='Customer')
    voucher_name = fields.Char(string='Receipt Voucher Number')
    receipt_name = fields.Char(string='Receipt Number')
    invoice_name = fields.Char(string='Invoice Number')

    _DATE_LABELS = {
        'voucher_date': 'Voucher Date', 'receipt_date': 'Receipt Date',
        'invoice_date': 'Invoice Date',
    }
    _STATUS_LABELS = {
        'all': 'All', 'draft': 'Draft', 'posted': 'Posted', 'cancel': 'Cancelled',
    }
    _AMOUNT_LABELS = {
        'invoice_total': 'Invoice Total',
        'amount_to_collect': 'Amount to Collect',
        'paid_to_date': 'Paid to Date',
        'residual': 'Residual Amount',
    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['company_id'] = self.env.company.id
        return super().create(vals_list)

    @property
    def date_type_label(self):
        return self._DATE_LABELS.get(self.date_type, '')

    @property
    def status_label(self):
        return self._STATUS_LABELS.get(self.status, '')

    @property
    def amount_basis_label(self):
        return self._AMOUNT_LABELS.get(self.amount_basis, '')

    @staticmethod
    def _contains(value, search):
        return not search or search.casefold() in (value or '').casefold()

    @staticmethod
    def _in_range(value, date_from, date_to):
        return value and date_from <= value <= date_to

    @staticmethod
    def _amount_from_line(line, amount_basis):
        return {
            'invoice_total': line.amount_total,
            'amount_to_collect': line.amount_to_collect,
            'paid_to_date': line.amount_paid_to_date,
            'residual': line.amount_residual,
        }[amount_basis]

    @property
    def _selected_statuses(self):
        return ['draft', 'posted', 'cancel'] if self.status == 'all' else [self.status]

    def _get_voucher_lines(self):
        domain = [
            ('voucher_id.company_id', '=', self.company_id.id),
            ('receipt_id.state', 'in', self._selected_statuses),
        ]
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        if self.voucher_name:
            domain.append(('voucher_id.name', 'ilike', self.voucher_name))
        if self.receipt_name:
            domain.append(('receipt_id.name', 'ilike', self.receipt_name))
        return self.env['account.receipt.voucher.line'].search(domain)

    def _get_report_rows(self):
        """Return one export row per invoice line linked to a receipt."""
        rows = []
        for voucher_line in self._get_voucher_lines():
            voucher = voucher_line.voucher_id
            receipt = voucher_line.receipt_id
            for receipt_line in receipt.line_ids:
                invoice_name = receipt_line.move_name or ''
                if self.invoice_name and not self._contains(invoice_name, self.invoice_name):
                    continue
                selected_date = {
                    'voucher_date': voucher.date,
                    'receipt_date': receipt.date,
                    'invoice_date': receipt_line.invoice_date,
                }[self.date_type]
                if not self._in_range(selected_date, self.date_from, self.date_to):
                    continue
                rows.append({
                    'partner_name': receipt.partner_id.display_name or '',
                    'voucher_name': voucher.name or '',
                    'voucher_date': voucher.date,
                    'receipt_name': receipt.name or '',
                    'receipt_date': receipt.date,
                    'invoice_name': invoice_name,
                    'invoice_date': receipt_line.invoice_date,
                    'amount': self._amount_from_line(receipt_line, self.amount_basis),
                    '_sort_key': (
                        voucher.date or fields.Date.to_date('1900-01-01'),
                        voucher.name or '',
                        receipt.date or fields.Date.to_date('1900-01-01'),
                        receipt.name or '',
                        receipt_line.invoice_date or fields.Date.to_date('1900-01-01'),
                        invoice_name,
                        receipt_line.id,
                    ),
                })
        rows.sort(key=lambda row: row.pop('_sort_key'))
        return rows

    @staticmethod
    def _validate_date_range(date_from, date_to):
        if date_from and date_to and date_from > date_to:
            raise ValidationError(_('Date From must be earlier than or equal to Date To.'))

    def action_export_xlsx(self):
        self.ensure_one()
        self._validate_date_range(self.date_from, self.date_to)
        if not self._get_report_rows():
            raise UserError(_('No receipt voucher records match the selected filters.'))
        report = self.env.ref('buz_receipt_export.action_receipt_voucher_xlsx')
        return report.report_action(self)
