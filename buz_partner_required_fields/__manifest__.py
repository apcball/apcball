{
    'name': 'Partner Required Fields for Company',
    'version': '17.0.1.0.0',
    'category': 'Contacts',
    'description': 'Enforce required fields (address, tax ID, phone, email, tax branch) for company-type partners.',
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': ['base', 'contacts', 'l10n_th_partner'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
}
