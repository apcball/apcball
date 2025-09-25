{
    "name": "HR Expense Advance Clearing",
    "summary": "Clear employee expenses from advance (141101) with VAT/WHT + audit trail",
    "version": "17.0.1.0.0",
    "author": "MOGEN IT",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": ["hr_expense", "account", "l10n_th_account_tax", "mail"],
        'data': [
        'security/ir.model.access.csv',
        'data/system_parameters.xml',
        'views/advance_box_views.xml',
        'views/hr_expense_views.xml',
        'views/hr_expense_config_views.xml',
        'wizard/advance_topup_wizard.xml',
        'wizard/advance_refill_base_wizard.xml',
        'wizard/advance_settlement_wizard.xml',
    ],
    "application": False,
    "installable": True
}