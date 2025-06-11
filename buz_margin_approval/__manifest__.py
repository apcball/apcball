# -*- coding: utf-8 -*-
{
    'name': 'buz Sales Margin Approval',
    'version': '1.0',
    'summary': 'Approve Sales Orders Based on Margin Rules',
    'description': """
        This module allows to set up margin approval rules for sales orders.
        When a sales order's margin falls below certain thresholds, 
        it requires approval from designated users before confirmation.
    """,
    'category': 'Sales',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['sale_management', 'sale_margin', 'sales_team'],
    'data': [
        'security/margin_approval_security.xml',
        'security/ir.model.access.csv',
        'views/margin_approval_views.xml',
        'views/sale_order_views.xml',
        'views/pending_approval_views.xml',
        'views/templates.xml',
        'views/report_margin_approval.xml',
        'views/margin_approval_dashboard.xml',
        'wizard/margin_approval_wizard_views.xml',
        'wizard/margin_rejection_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
