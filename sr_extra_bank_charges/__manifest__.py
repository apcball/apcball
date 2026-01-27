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
    'version': '17.0.1.0',
    'category': 'Accounting',
    "license": "OPL-1",
    'summary': 'Additional charges in Thai Baht (THB), extra transaction bank fee, credit card charge, extra fee on bank transfer, additional charges on bank money transfer, THB only bank charges regardless of bill currency',
    'description': """
    Additional Charges in Thai Baht (THB)
    ===========================================
    
    This module allows you to add bank charges in Thai Baht (THB) currency only,
    regardless of the invoice/bill currency (USD, EUR, etc.).
    
    Features:
    - Bank charges always in THB
    - Automatic currency conversion for accounting entries
    - Separate journal entries for bank charges
    - Support for foreign currency invoices with THB bank charges
    - Proper exchange rate handling
    
    Key Benefits:
    - Bank charges in local currency (THB) only
    - Multi-currency support with THB bank fees
    - Accurate accounting with proper currency conversion
    - Separate tracking of bank charges
""",
    "price": 10,
    "currency": 'EUR',
    'author': 'Sitaram',
    'depends': ['base','account'],
    'data': [
             'views/sr_inherit_journal.xml',
             'views/sr_inherit_account_payment_views.xml',
             'wizards/sr_inherit_account_payment_register_views.xml'
    ],
    'website':'https://sitaramsolutions.in',
    'installable': True,
    'auto_install': False,
    'live_test_url':'www.sitaramsolutions.in',
    "images":['static/description/banner.png'],
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
