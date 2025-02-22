{
    'name': 'buz_Advance Payment in Purchase',
    'version': '17.0',
    'category': 'Accounting',
    'summary': 'Advance Payment in Purchase',
    'author': 'INKERP',
    'website': 'https://www.INKERP.com/',
    'depends': ['account', 'purchase'],

    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'wizard/advance_payments_wizard_view.xml',
        'views/purchase_order_view.xml',
    ],

    'images': ['static/description/banner.png'],
    'license': "OPL-1",
    'installable': True,
    'application': True,
    'auto_install': False,
}
