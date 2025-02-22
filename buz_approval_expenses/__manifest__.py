{
    'name': 'Business Approval Expenses',
    'version': '1.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Add approval workflow to expenses',
    'description': """
    Add approval workflow to expenses with manager and ACC manager approval steps.
    """,
    'depends': [
        'base',
        'hr_expense',
        'mail',
        'base_setup',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/hr_expense_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_expense_refuse_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}