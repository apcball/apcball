{
    'name': 'Share Certificate Print',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Fill and print a Thai share certificate',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'report/share_certificate_report.xml',
        'views/share_certificate_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
