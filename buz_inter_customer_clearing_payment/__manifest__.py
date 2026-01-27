# -*- coding: utf-8 -*-
{
    'name': 'Inter-Customer Clearing Payment',
    'version': '17.0.2.0.0',
    'category': 'Accounting',
    'summary': 'Receive payments from one customer and allocate to invoices of multiple customers with credit note support',
    'description': """
Inter-Customer Clearing Payment Module
=====================================

This module allows users to receive a lump-sum payment from one customer and
allocate it to invoices of multiple customers using inter-customer clearing logic.

Key Features:
------------
* User-friendly 4-step wizard (Payment → Credit Notes → Invoices → Review)
* Support for partial payments
* Credit Note support - use credit notes along with payments
* Multi-currency support with automatic FX handling
* Cancel and reverse functionality
* 100% accounting-correct and audit-safe
* No manual reconciliation required

Business Scenario:
-----------------
* Customers are separated by branch (each branch = different customer record)
* One branch/customer sends a lump-sum payment
* That payment must be used to settle invoices of other customers/branches
* Master data CANNOT be changed
* AR Aging and audit trail remain correct

Menu Location:
--------------
Accounting → Customers → Receive Clearing Payment
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'account_payment',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/clearing_payment_wizard_views.xml',
        'views/account_move_views.xml',
        'views/clearing_payment_menu.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'sequence': 100,
    'images': [],
}