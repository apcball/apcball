{
    'name': 'Employee Advance',
    'version': '17.0.1.0.6',
    'category': 'Human Resources',
    'summary': 'Employee Advance Management with Advance Box and Bill Clearing',
    'description': """
        This module implements a complete workflow for employee advances:
        - Maintain Advance Box per employee with Refill-to-Base functionality
        - Submit expenses and clear from advance
        - Create draft vendor bills after manager approval
        - Clear advances with payment wizard
        - Support for VAT/WHT reporting
        - Clearing mode: Reimburse Employee
        - Settlement functionality for closing advance boxes
        - NEW: Separate bills for same employee with different dates
        - NEW: Group by partner and date for proper accounting separation
        - NEW: Use expense sheet date as accounting date in bills
        - NEW: Each expense line creates a separate invoice line (no grouping by product)
        - NEW: Cancel button for refill history (both draft and posted states)
        - FIXED: Expense lines with same product code now remain separate in bills
        - FIXED: WHT Clear Advance reconcile now only with specific bill (not other bills)
    """,
    'author': 'Apichart Ball',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'hr_expense',
        'account',
        'mail',
        'hr_contract',
        'l10n_th_account_tax',
        'l10n_th_account_wht_cert_form',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_activity_types.xml',
        'data/batch_actions.xml',
        'data/wht_taxes.xml',
        'views/actions.xml',
        'views/advance_box_views.xml',
        'views/expense_sheet_views.xml',
        'views/hr_expense_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/wizard_views.xml',
        'views/account_move_views.xml',
        'wizards/mark_as_done_confirmation_wizard.xml',  # Add the wizard view
        'views/wht_clear_advance_wizard_views.xml',
        'views/advance_refill_base_wizard_views.xml',  # Refill wizard view
        'views/advance_settlement_wizard_views.xml',   # Settlement wizard view
        'views/advance_box_refill_views.xml',  # Refill history views
        'views/wizard_refill_advance_box_views.xml',  # New refill wizard
        'views/advance_box_refill_menus.xml',  # Refill menus
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'application': True,
}