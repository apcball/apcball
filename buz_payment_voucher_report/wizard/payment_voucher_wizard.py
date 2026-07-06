# -*- coding: utf-8 -*-
"""
Payment Voucher Report Wizard

TransientModel wizard for filtering, sorting, grouping, and printing
Payment Voucher reports in PDF or XLSX format.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PaymentVoucherWizard(models.TransientModel):
    """
    Payment Voucher Report Wizard

    Allows users to filter payments by date range, partner, journal,
    company, payment type, and state. Supports sorting, grouping,
    and display options.

    Output formats: PDF or XLSX.
    """
    _name = 'buz.payment.voucher.wizard'
    _description = 'Payment Voucher Report Wizard'

    # Date filters
    date_from = fields.Date(
        string='Date From',
        help='Start date for payment filter'
    )
    date_to = fields.Date(
        string='Date To',
        help='End date for payment filter'
    )

    # Entity filters
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        domain=['|', ('parent_id', '=', False), ('is_company', '=', True)],
        help='Filter by customer or vendor'
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        domain=[('type', 'in', ('bank', 'cash', 'general'))],
        help='Filter by payment journal'
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        help='Filter by company'
    )

    # Payment attributes
    payment_type = fields.Selection(
        selection=[
            ('inbound', 'Customer Payment'),
            ('outbound', 'Vendor Payment'),
            ('transfer', 'Internal Transfer'),
        ],
        string='Payment Type',
        help='Filter by payment type'
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('sent', 'Sent'),
            ('reconciled', 'Reconciled'),
        ],
        string='State',
        help='Filter by payment state'
    )

    # Sort options
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
        help='Sort payments by selected field'
    )

    # Group options
    group_by = fields.Selection(
        selection=[
            ('none', 'No Grouping'),
            ('partner_id', 'Partner'),
            ('journal_id', 'Journal'),
            ('payment_method_id', 'Payment Method'),
        ],
        string='Group By',
        default='none',
        required=True,
        help='Group payments by selected field'
    )

    # Output format
    output_format = fields.Selection(
        selection=[
            ('pdf', 'PDF'),
            ('xlsx', 'Excel (XLSX)'),
        ],
        string='Output Format',
        default='pdf',
        required=True,
        help='Select report output format'
    )

    # Display options (checkboxes)
    show_account_code = fields.Boolean(
        string='Show Account Code',
        default=True,
        help='Display account code column'
    )
    show_account_name = fields.Boolean(
        string='Show Chart of Account',
        default=True,
        help='Display chart of account column'
    )
    show_line_partner = fields.Boolean(
        string='Show Partner',
        default=True,
        help='Display partner column on journal items'
    )
    show_label = fields.Boolean(
        string='Show Label',
        default=True,
        help='Display label/description column'
    )
    show_ref = fields.Boolean(
        string='Show Reference',
        default=True,
        help='Display payment reference'
    )
    show_memo = fields.Boolean(
        string='Show Memo',
        default=True,
        help='Display payment memo'
    )
    show_analytic = fields.Boolean(
        string='Show Analytic Account',
        default=True,
        help='Display analytic account column'
    )
    show_currency = fields.Boolean(
        string='Show Currency',
        default=True,
        help='Display currency column'
    )
    show_amount_currency = fields.Boolean(
        string='Show Amount Currency',
        default=True,
        help='Display amount in currency column'
    )
    show_reconciled = fields.Boolean(
        string='Show Reconciled Invoices',
        default=True,
        help='Display reconciled invoices/bills section'
    )

    def _build_domain(self):
        """
        Build domain for searching account.payment records.

        :return: domain list for account.payment search
        :rtype: list
        """
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

    def _get_sort_order(self):
        """
        Get ORDER BY clause based on sort_by selection.

        :return: sort order string
        :rtype: str
        """
        sort_map = {
            'payment_date': 'payment_date ASC, payment_name ASC',
            'payment_name': 'payment_name ASC, payment_date ASC',
            'partner_id': 'partner_id ASC, payment_date ASC',
            'journal_id': 'journal_id ASC, payment_date ASC',
        }
        return sort_map.get(self.sort_by, 'payment_date ASC')

    def action_generate(self):
        """
        Generate report data and display in tree view.

        Creates buz.payment.voucher records (SQL view) and returns
        a tree view action filtered by selected payments.

        :return: Tree view action
        :rtype: dict
        """
        self.ensure_one()
        domain = self._build_domain()

        # Get payments based on filters
        payments = self.env['account.payment'].search(domain)
        if not payments:
            raise UserError(_('No payments found for the selected criteria.'))

        # Get move IDs from payments
        move_ids = payments.mapped('move_id').ids
        if not move_ids:
            raise UserError(_('Selected payments have no journal entries.'))

        # Search payment voucher records (SQL view)
        pv_domain = [('payment_id', 'in', payments.ids)]
        voucher_records = self.env['buz.payment.voucher'].search(pv_domain)

        if not voucher_records:
            raise UserError(_('No journal items found for selected payments.'))

        # Return tree view action
        action = self.env.ref(
            'buz_payment_voucher_report.action_payment_voucher_tree_view'
        ).read()[0]
        action['domain'] = [('id', 'in', voucher_records.ids)]
        action['context'] = {
            'group_by': self.group_by if self.group_by != 'none' else False,
            'show_account_code': self.show_account_code,
            'show_account_name': self.show_account_name,
            'show_line_partner': self.show_line_partner,
            'show_label': self.show_label,
            'show_ref': self.show_ref,
            'show_memo': self.show_memo,
            'show_analytic': self.show_analytic,
            'show_currency': self.show_currency,
            'show_amount_currency': self.show_amount_currency,
            'show_reconciled': self.show_reconciled,
        }
        return action

    def action_print_pdf(self):
        """
        Print Payment Voucher report in PDF format.

        :return: Report action for PDF download
        :rtype: dict
        """
        self.ensure_one()
        domain = self._build_domain()
        payments = self.env['account.payment'].search(domain)

        if not payments:
            raise UserError(_('No payments found for the selected criteria.'))

        return self.env.ref(
            'buz_payment_voucher_report.action_report_payment_voucher'
        ).report_action(payments)

    def action_print_xlsx(self):
        """
        Print Payment Voucher report in XLSX format.

        :return: Report action for XLSX download
        :rtype: dict
        """
        self.ensure_one()
        domain = self._build_domain()
        payments = self.env['account.payment'].search(domain)

        if not payments:
            raise UserError(_('No payments found for the selected criteria.'))

        return self.env.ref(
            'buz_payment_voucher_report.action_report_payment_voucher_xlsx'
        ).report_action(payments)
