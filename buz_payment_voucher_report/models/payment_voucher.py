# -*- coding: utf-8 -*-
"""
Payment Voucher Report Model

SQL view model that joins account.payment with account.move.line
to display complete journal entries for each payment.

Data source: account.payment.move_id.line_ids
Never calculate accounting values manually - always use Odoo's journal entry.
"""
import logging

from odoo import api, fields, models, tools

_logger = logging.getLogger(__name__)


class PaymentVoucherReport(models.Model):
    """
    Payment Voucher Report SQL View Model

    This model provides a read-only view of payment voucher data by joining
    account.payment with account.move.line through move_id.

    The SQL view ensures:
    - No manual calculation of accounting values
    - Always uses Odoo's generated journal entry
    - Supports multi-company and multi-currency
    """
    _name = 'buz.payment.voucher'
    _description = 'Payment Voucher Report'
    _auto = False
    _order = 'payment_date desc, payment_name'

    # Payment header fields
    payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Payment',
        readonly=True,
        help='Source payment record'
    )
    payment_name = fields.Char(
        string='Payment Number',
        readonly=True,
        help='Payment reference number'
    )
    payment_date = fields.Date(
        string='Payment Date',
        readonly=True,
        help='Date of the payment'
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        readonly=True,
        help='Customer or Vendor'
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        readonly=True,
        help='Payment journal'
    )
    payment_method_id = fields.Many2one(
        comodel_name='account.payment.method',
        string='Payment Method',
        readonly=True,
        help='Payment method (Bank, Cash, Check, etc.)'
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        readonly=True,
        help='Payment currency'
    )
    payment_type = fields.Selection(
        selection=[
            ('inbound', 'Customer Payment'),
            ('outbound', 'Vendor Payment'),
            ('transfer', 'Internal Transfer'),
        ],
        string='Payment Type',
        readonly=True,
        help='Type of payment'
    )
    ref = fields.Char(
        string='Reference',
        readonly=True,
        help='Payment reference'
    )
    memo = fields.Char(
        string='Memo',
        readonly=True,
        help='Payment memo/narration'
    )
    created_by = fields.Many2one(
        comodel_name='res.users',
        string='Created By',
        readonly=True,
        help='User who created the payment'
    )
    move_name = fields.Char(
        string='Move Number',
        readonly=True,
        help='Journal entry number'
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        readonly=True,
        help='Company'
    )

    # Journal item (move line) fields
    move_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Journal Item',
        readonly=True,
        help='Source journal item'
    )
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account',
        readonly=True,
        help='General ledger account'
    )
    account_code = fields.Char(
        string='Account Code',
        readonly=True,
        help='General ledger account code'
    )
    account_name = fields.Char(
        string='Chart of Account',
        readonly=True,
        help='General ledger account name'
    )
    line_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Line Partner',
        readonly=True,
        help='Partner on journal item (for receivable/payable lines)'
    )
    label = fields.Char(
        string='Label',
        readonly=True,
        help='Journal item label/description'
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        readonly=True,
        help='Analytic account on journal item'
    )
    amount_currency = fields.Monetary(
        string='Amount Currency',
        currency_field='currency_id',
        readonly=True,
        help='Amount in payment currency'
    )
    debit = fields.Monetary(
        string='Debit',
        currency_field='company_currency_id',
        readonly=True,
        help='Debit amount in company currency'
    )
    credit = fields.Monetary(
        string='Credit',
        currency_field='company_currency_id',
        readonly=True,
        help='Credit amount in company currency'
    )
    company_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Company Currency',
        readonly=True,
        help='Company currency for debit/credit'
    )


    def init(self):
        """
        Initialize the SQL view for payment voucher report.

        The view joins:
        - account_payment (payment header)
        - account_move (journal entry)
        - account_move_line (journal items)
        - account_account (account code and name)
        - account_move_line matched credits/debits (for reconciled invoices)

        This ensures we always use Odoo's generated journal entry values.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    -- Unique ID using row number (window function)
                    ROW_NUMBER() OVER () AS id,
                    -- Payment header fields (from account_move since account_payment lacks some columns)
                    ap.id AS payment_id,
                    COALESCE(ap.payment_reference, am.name, 'Payment ' || ap.id::text) AS payment_name,
                    am.date AS payment_date,
                    ap.partner_id AS partner_id,
                    am.journal_id AS journal_id,
                    ap.payment_method_id AS payment_method_id,
                    ap.currency_id AS currency_id,
                    ap.payment_type AS payment_type,
                    ap.payment_reference AS ref,
                    ap.payment_reference AS memo,
                    am.create_uid AS created_by,
                    am.name AS move_name,
                    am.company_id AS company_id,
                    -- Journal item fields
                    aml.id AS move_line_id,
                    aml.account_id AS account_id,
                    aa.code AS account_code,
                    aa.name AS account_name,
                    aml.partner_id AS line_partner_id,
                    aml.name AS label,
                    NULL AS analytic_account_id,
                    aml.amount_currency AS amount_currency,
                    aml.debit AS debit,
                    aml.credit AS credit,
                    aml.company_currency_id AS company_currency_id
                FROM account_payment ap
                INNER JOIN account_move am ON am.id = ap.move_id
                INNER JOIN account_move_line aml ON aml.move_id = am.id
                INNER JOIN account_account aa ON aa.id = aml.account_id
                WHERE am.state IN ('posted', 'sent', 'reconciled')
            )
        """ % self._table)
        _logger.info('Payment Voucher Report SQL view created/updated: %s', self._table)

    def get_payment_totals(self, payment_id):
        """
        Calculate total debit and credit for a payment.

        :param payment_id: ID of account.payment
        :return: dict with total_debit, total_credit, difference
        """
        self.ensure_one()
        records = self.search([('payment_id', '=', payment_id)])
        total_debit = sum(records.mapped('debit'))
        total_credit = sum(records.mapped('credit'))
        difference = total_debit - total_credit
        return {
            'total_debit': total_debit,
            'total_credit': total_credit,
            'difference': difference,
            'is_balanced': abs(difference) < 0.01,
        }

