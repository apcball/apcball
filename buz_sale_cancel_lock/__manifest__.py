{
    'name': 'buz Sale Cancel Lock',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Block cancelling Sales Orders that already have a posted invoice',
    'description': """
        Sales Orders with at least one posted customer invoice (including
        invoices already reversed by a credit note) can no longer be cancelled.
        Cancel or reset the invoice first. Draft invoices do not block.
    """,
    'author': 'BUZ',
    'website': 'https://www.buz.co.th',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'account',
    ],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
