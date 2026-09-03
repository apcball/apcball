{
    'name': 'Partner Required Fields for Company',
    'version': '17.0.1.1.5',
    'category': 'Contacts',
    'description': (
        'Enforce required fields (address, phone, email) for company-type '
        'and standalone individual partners; tax ID is required for '
        'company-type only, tax branch is required for company-type only.'
    ),
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': ['base', 'contacts', 'l10n_th_partner'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
}
