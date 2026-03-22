# -*- coding: utf-8 -*-
{
    'name': 'Sale Invoice Policy Bypass',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Bypass invoicing policy restriction on Sale Orders',
    'description': """
        Allows users to create invoices on Sale Orders regardless of:
        - Product invoicing policy (Ordered vs Delivered quantities)
        - Delivery status
        - Quantity delivered

        Intended for temporary use (e.g., accounting backlog processing).
    """,
    'author': 'Custom',
    'depends': ['sale'],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
