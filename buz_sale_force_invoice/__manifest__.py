{
    'name': 'buz Sale Force Invoice',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Force invoice creation on Sales Orders without delivery',
    'description': """
        Allows authorized users to create Customer Invoices directly from
        Sales Orders even when products have not been delivered yet.

        For exceptional cases requiring invoicing before delivery:
        bank discounting, bill exchange, letter of credit, financing.
    """,
    'author': 'BUZ',
    'website': 'https://www.buz.co.th',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'account',
        'stock',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
        'views/sale_force_invoice_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
