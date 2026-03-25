# -*- coding: utf-8 -*-
{
    'name': 'Weekly Budget Control',
    'version': '17.0.1.0.0',
    'category': 'Purchase',
    'summary': 'Weekly budget control for purchase orders',
    'description': """
        Weekly Budget Control Module
        ============================
        - Define weekly budget plans with date ranges
        - Auto-generate weekly budget lines (Monday-Sunday)
        - Block PO confirmation when weekly budget is exceeded
        - Email notification when budget is exceeded
        - Budget check on Purchase Orders and Purchase Requisitions
        - Budget adjustment wizard with audit trail
        - Company-wide or all-companies budget scope
        - Modern OWL Smart Dashboard with Chart.js
    """,
    'author': 'KYLD',
    'depends': [
        'web',
        'purchase',
        'mail',
        'employee_purchase_requisition',
        'job_costing_management',
        'buz_po_portal',
    ],
    'data': [
        'security/budget_security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/mail_template_data.xml',
        'wizard/budget_adjustment_wizard_views.xml',
        'wizard/budget_reason_wizards_views.xml',
        'views/weekly_budget_plan_views.xml',
        'views/weekly_budget_line_views.xml',
        'views/weekly_budget_report_views.xml',
        'views/dashboard_views.xml',
        'views/budget_approval_request_views.xml',
        'views/purchase_order_views.xml',
        'views/purchase_requisition_views.xml',
        'views/material_requisition_views.xml',
        'views/procurement_pool_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'biz_weekly_budget/static/src/scss/budget_dashboard.scss',
            'biz_weekly_budget/static/src/js/budget_dashboard.js',
            'biz_weekly_budget/static/src/xml/budget_dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
