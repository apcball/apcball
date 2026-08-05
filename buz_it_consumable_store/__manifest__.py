{
    'name': 'IT Consumable Store',
    'version': '17.0.1.0.0',
    'category': 'Services/IT',
    'summary': 'Standalone IT consumable store and requisition (Phase 1)',
    'description': """
IT Consumable Store Phase 1
===========================

Standalone IT consumable requisition system with its own stock.

* Store card page to pick multiple consumable items into one request
* Request header with multiple lines (draft -> รอจ่าย -> จ่ายบางส่วน -> เสร็จสิ้น)
* IT delivers per line or all at once; stock is deducted only on delivery
* Standalone IT stock: locations, on-hand balance, receive / adjust / history
* No dependency on the main Inventory module (no stock.quant / stock.move)
* Reuses the IT Management menu and the IT requester / support / manager groups
* Asset lend-return remains unchanged (out of scope)
    """,
    'author': 'BUZ',
    'license': 'LGPL-3',
    'depends': [
        'buz_it_helpdesk',
        'hr',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/consumable_views.xml',
        'views/stock_views.xml',
        'views/request_views.xml',
        'views/wizard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_it_consumable_store/static/src/scss/consumable_store.scss',
        ],
    },
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}
