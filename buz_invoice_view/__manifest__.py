{
    'name': 'Buz Invoice View',
    'version': '17.0.1.0.3',
    'summary': 'Display Client Order Reference from Sale Order on Invoice',
    'description': 'This module adds the Client Order Reference (Customer PO) from linked Sale Orders to the Invoice form view.',
    'category': 'Accounting',
    'author': 'apcball',
    'depends': ['account', 'sale', 'buz_custom_invoice'],
    'data': [
        'views/account_move_view.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
