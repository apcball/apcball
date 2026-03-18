{
    'name': 'Multi-Rate Currency (Buy/Sell)',
    'version': '17.0.1.0.0',
    'summary': 'Support Buy and Sell exchange rates for currencies',
    'description': """
        This module extends the standard Odoo currency system to support 
        different exchange rates for buying and selling.
        - Adds Buy Rate and Sell Rate to currency rates.
        - Provides context support for rate selection (rate_type: 'buy' | 'sell' | 'standard').
        - Automatic fallback to standard rate if buy/sell rates are not defined.
    """,
    'category': 'Accounting/Accounting',
    'author': 'Your Company',
    'website': 'https://yourwebsite.com',
    'license': 'LGPL-3',
    'depends': ['base', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/currency_rate_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
