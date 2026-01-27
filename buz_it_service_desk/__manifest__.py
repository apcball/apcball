# -*- coding: utf-8 -*-
{
    'name': 'IT Service Desk',
    'version': '17.0.1.0.0',
    'category': 'Helpdesk',
    'summary': 'Complete IT Service Desk Management System',
    'description': """
IT Service Desk Management
==========================

This module provides a complete IT Service Desk solution for managing:
- IT Incidents (Hardware/Software problems)
- IT Service Requests (System access/permission)
- IT Purchase Requests (Request to buy IT equipment)

Features:
* Centralized ticket management system
* SLA tracking and monitoring
* Approval workflows
* Activity tracking and notifications
* Security groups with proper access control
* Dashboard for monitoring and reporting
    """,
    'author': 'BUZ',
    'website': 'https://www.buz.co.th',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'hr',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/activity_type.xml',
        'data/mail_template.xml',
        'views/it_category_views.xml',
        'views/it_ticket_views.xml',
        'views/it_service_request_views.xml',
        'views/it_purchase_request_views.xml',
        'views/dashboard.xml',
        'views/menu.xml',
        'wizard/approve_wizard_view.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 100,
}