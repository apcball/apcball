{
    'name': 'Share Certificate',
    'version': '17.0.1.0.0',
    'category': 'Administration',
    'summary': 'Prepare and print share certificates',
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'report/share_certificate_report.xml',
        'wizard/share_certificate_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_share_certificate/static/src/scss/share_certificate_dialog.scss',
            'buz_share_certificate/static/src/js/report_actions.js',
        ],
    },
    'application': True,
    'installable': True,
}
