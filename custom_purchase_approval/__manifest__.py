{
    'name': 'buz Custom Purchase Approval',
    'version': '1.0',
    'category': 'Purchase',
    'summary': 'Custom purchase order approval workflow',
    'description': """
        Custom module for purchase order approval:
        - Two level approval process based on amount
        - Level 1 approval for amount <= 50000
        - Level 2 approval for amount > 50000
    """,
    'depends': ['purchase', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/purchase_view.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}