{
    'name': 'Warranty Customer Registration Portal',
    'version': '17.0.1.0.0',
    'category': 'Customer Service',
    'summary': 'Customer-facing warranty registration via QR code and public web form',
    'author': 'apcball',
    'license': 'LGPL-3',
    'depends': [
        'buz_warranty_management',
        'website',
        'portal',
        'mail',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/warranty_portal_templates.xml',
        'views/warranty_card_views.xml',
        'views/warranty_portal_qr_wizard_views.xml',
    ],
    'application': False,
    'auto_install': False,
}