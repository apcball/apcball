# -*- coding: utf-8 -*-
{
    'name': 'Budget Engine Core',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Budget',
    'summary': 'Core budget engine and commitment tracking for budget control modules',
    'description': """
        Budget Engine Core
        ==================
        Provides a reusable budget engine service and commitment tracking system.

        Features:
        - budget.commitment model: records all budget reservations and consumption
        - budget.engine abstract model: check, reserve, consume, release budget
        - Designed to be extended by biz_weekly_budget and biz_monthly_analytic_budget
    """,
    'author': 'APCBALL',
    'depends': [
        'base',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
