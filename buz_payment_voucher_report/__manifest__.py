# -*- coding: utf-8 -*-
{
    'name': 'Payment Voucher Report',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Payment Voucher Excel Export for Odoo 17',
    'description': """
        Payment Voucher Excel export for accountants and auditors.

        Features:
        - Export professional Accounting Payment Voucher to XLSX
        - Shows complete journal entries from account.payment
        - Supports Customer Payment, Vendor Payment, Internal Transfer
        - Filter by partner, journal, company, payment type, state
        - Sort by payment date, number, partner, journal
        - Multi-company and multi-currency support
    """,
    'author': 'Mogen Co.',
    'website': 'https://www.mogen.co.th',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'mail',
        'report_xlsx',
    ],
    'data': [
        'security/ir.model.access.csv',
        'report/report_action.xml',
        'wizard/payment_voucher_wizard_view.xml',
        'views/account_payment_view.xml',
        'views/payment_voucher_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
