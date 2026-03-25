# -*- coding: utf-8 -*-
{
    'name': 'Monthly Analytic Budget (Mogen)',
    'version': '17.0.1.0.0',
    'category': 'Purchase',
    'summary': 'Monthly budget allocation and control based on analytic accounts',
    'description': """
        Monthly Analytic Budget Control
        ================================
        - Define monthly budget plans with total budget amounts
        - Allocate budget to analytic accounts by percentage or fixed amount
        - Validate purchase requisitions against monthly analytic budgets
        - Reserve budget on PR approval, convert to used on PO confirmation
        - Prevent duplicate analytic accounts in the same monthly plan
        - Multi-company support
    """,
    'author': 'APCBALL',
    'depends': [
        'budget_engine_core',
        'purchase',
        'account',
        'mail',
        'employee_purchase_requisition',
    ],
    'data': [
        'security/budget_security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/monthly_budget_plan_views.xml',
        'views/monthly_budget_line_views.xml',
        'views/monthly_budget_approval_request_views.xml',
        'wizard/monthly_budget_reason_wizards_views.xml',
        'views/purchase_order_views.xml',
        'views/purchase_requisition_views.xml',
        'views/monthly_budget_report_views.xml',
        'views/menu_views.xml',
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'biz_monthly_analytic_budget/static/src/scss/monthly_budget_dashboard.scss',
            'biz_monthly_analytic_budget/static/src/js/monthly_budget_dashboard.js',
            'biz_monthly_analytic_budget/static/src/xml/monthly_budget_dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
