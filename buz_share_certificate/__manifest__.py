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
        'wizard/share_certificate_wizard_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            '/buz_share_certificate/static/src/css/share_certificate_report.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
