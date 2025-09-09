{
    'name': 'buz Account Pdc',
    'summary': """ Extension on Cheques to handle Post Dated Cheques """,
    'description': """ Extension on Cheques to handle Post Dated Cheques """,

    'author': 'Adevx',
    'category': 'Accounting/Accounting',
    "license": "OPL-1",
    'website': 'https://adevx.com',

    'depends': ['account_check_printing', 'sale'],
    'data': [
        'data/account_pdc_data.xml',
        'views/account_payment.xml',
        'views/sale_order.xml',
    ],

    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
