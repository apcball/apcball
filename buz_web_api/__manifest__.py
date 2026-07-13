{
    'name': 'Web API Integration for Odoo',
    'version': '17.0.1.0.0',
    'category': 'Technical Settings',
    'summary': 'Secure native Odoo API key provisioning for web integrations',
    'description': """
Web API Integration for Odoo
============================
Provides system administrators with integration metadata and a one-time
API-key generation flow backed by Odoo's native res.users.apikeys model.
The addon also exposes a protected health endpoint for web-to-Odoo checks.
    """,
    'author': 'MOGEN',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'buz_warranty_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/web_api_integration_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
