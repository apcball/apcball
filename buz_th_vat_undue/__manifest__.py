{
    'name': 'Thailand VAT Undue Management',
    'version': '17.0.1.0.8',
    'category': 'Accounting/Localization',
    'summary': 'Manage Thailand VAT Undue (Tax Suspense)',
    'description': """
        This module allows managing Thailand VAT Undue (Purchase Tax not yet due).
        - Configure VAT Undue Taxes
        - Defer VAT posting to a VAT Undue account
        - Manage VAT Undue via a dedicated screen
        - Batch convert VAT Undue to Input VAT
        - Integration with Thai Tax Reports
    """,
    'author': 'APCBALL',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'account',
        'l10n_th',
        'l10n_th_account_tax',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_tax_views.xml',
        'views/account_move_view.xml',
        'views/tax_undue_views.xml',
        'views/menu.xml',
        'wizard/vat_undue_use_wizard_views.xml',
        'wizard/vat_undue_diagnostic_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
