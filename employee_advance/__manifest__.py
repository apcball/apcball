{
    'name': 'Employee Advance',
    'version': '17.0.1.0.0',
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
    """,
    'author': 'Your Company',
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
        'views/actions.xml',
        'views/advance_box_views.xml',
        'views/expense_sheet_views.xml',
        'views/hr_expense_views.xml',
        'views/res_config_settings_views.xml',
        'views/wizard_views.xml',
        'views/account_move_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'application': True,
}