{
    'name': 'buz Dynamic Bank Cheque Printing',
    'version': '17.0.1.0.0',
    'summary': 'Dynamic Cheque Printing.',
    'description': """
        Dynamic Cheque Printing.
            ** Added Unit No field in the Fleet Module. 
    """,
    'category': 'website',
    'author': 'Silver Touch Technologies Limited',
    'website': 'https://www.silvertouch.com',
    'images':['static/description/banner.png'],
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'website','web'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/cheque_print.xml',
        'wizard/cheque_report.xml',
        'wizard/cheque_print_preview_report.xml',
        'wizard/cheque_attribute_wizard.xml',
        'views/bank_cheque.xml',
        'views/bank_cheque_leaf.xml',
        'views/chequebook.xml',
        'views/cheque_attribute.xml',
        "views/account_payment.xml",
        "views/cheque_configure_template.xml",
        "views/cheque_attribute_template.xml",
        "reports/bank_cheque_report.xml",
        "reports/cheque_repot_template.xml",
        "reports/cheque_format_templates.xml",
        "reports/bank_cheque_preview.xml",
    ],

    'assets': {
        'web.assets_frontend': [
            # 'sttl_dynamic_bank_cheque_print/static/src/js/cheque_attribute.js',
            'sttl_dynamic_bank_cheque_print/static/src/css/cheque_print.css',
        ],
        'web.assets_backend': [
            'sttl_dynamic_bank_cheque_print/static/src/js/cheque_configure.js',
            'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css',
            'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js',
        ]
    },
    'installable': True,
    'auto_install': False
}