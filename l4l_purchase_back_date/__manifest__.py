# -*- coding: utf-8 -*-
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2023 Leap4Logic Solutions PVT LTD
#    Email : sales@leap4logic.com
#################################################

{
    'name': 'Purchase Back Date',
    'category': 'Inventory/Purchase',
    'version': '17.0.1.0',
    'sequence': 5,
    'summary': 'BackDate in Purchase Order, Set BackDate in Purchase, Stock, Sale, Sale Order, Purchase, Purchase Order, Inventory, Transfer, Invoice',
      'description': "This Module Simplifies The Task of Backdating Transactions in Purchase Order by Allowing Users to Adjust Order Dates During Confirmation. This Helps Ensure that Associated Documents, like Receipt Schedules and Accounting Entries, Correctly Reflect the Selected Date, Ultimately Making Transaction Timelines more Efficient in Odoo.",
    'author': 'Leap4Logic Solutions Private Limited',
    'website': 'https://leap4logic.com/',
    'depends': ['purchase', 'stock', 'sale_stock'],
    'data': [
        'views/res_config_views.xml',
    ],
    'installable': True,
    'application': True,
    'images': ['static/description/banner.gif'],
    'license': 'OPL-1',
    "price": 11.99,
    "currency": "USD",
    "live_test_url": 'https://youtu.be/T0U10a7Ib-k',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
