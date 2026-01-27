# -*- coding: utf-8 -*-
{
    'name': 'LINE Portal Notification',
    'version': '17.0.2.0.0',
    'category': 'Tools',
    'summary': 'Send LINE notifications with secure portal links for document approval',
    'description': """
LINE Notification + Portal Approval Link
=========================================

This module enables sending LINE notifications with secure portal links for document approval.

Features:
---------
* Generate secure, single-use portal tokens
* Send LINE push messages with approval links
* Portal page for document review and approval
* Complete audit trail for all approval actions
* Rate limiting for security
* Configurable token expiry
* LINE Webhook for automatic User ID capture
* LINE User mapping to Odoo users/employees

Configuration:
--------------
1. Go to Settings > General Settings > LINE Notification
2. Enter your LINE Channel Access Token and Channel Secret
3. Configure webhook URL in LINE Developers Console: https://your-domain.com/line/webhook
4. LINE Users will be automatically captured when they message your Official Account
5. Map LINE Users to Odoo users/employees in Settings > LINE > LINE Users

Usage:
------
1. On documents with 'waiting_approval' state, click "Send LINE Approval Request"
2. Approver receives LINE message with portal link
3. Approver reviews and approves/rejects via portal
4. Full audit trail is recorded
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'portal',
        'hr',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/system_parameters.xml',
        # Views
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'views/approval_token_views.xml',
        'views/approval_audit_log_views.xml',
        'views/portal_templates.xml',
        'views/line_channel_verification_views.xml',
        'views/line_user_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'line_portal_notification/static/src/css/portal_approval.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
