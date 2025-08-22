# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

{
    'name': 'Extra Bank Charges In Payments',
    'version': '17.0.0.0',
    'category': 'Accounting',
    "license": "OPL-1",
    'summary': 'Additional charges, extra transaction bank fee, credit card charge, extra fee on bank transfer, additional charges on bank money transfer, gst charges on bank transfers, government tax on foreign transaction, gst on foreign transaction, fixed bank charges on foreign transaction, foreign transaction bank fee, foreign transaction bank charges',
    'description': """
    Additional Charges
    Credit Card Charges
    Transfer charges
    transfer fees
    foreign transfer charges
    foreign currency transfer fee
    payment fee on vendor bills
    extra bank charges
    extra bank fee
    fees on payment
    transaction fee
    extra credit card charges
    extra credit card fee
    separate journal entry for bank fee
    separate journal entry for bank charges
    bank fee
    bank charges
    maintenance charge
    security charges
""",
    "price": 10,
    "currency": 'EUR',
    'author': 'Sitaram',
    'depends': ['base','account'],
    'data': [
             'views/sr_inherit_journal.xml',
             'wizards/sr_inherit_account_payment_register_views.xml'
    ],
    'website':'https://sitaramsolutions.in',
    'installable': True,
    'auto_install': False,
    'live_test_url':'www.sitaramsolutions.in',
    "images":['static/description/banner.png'],
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
