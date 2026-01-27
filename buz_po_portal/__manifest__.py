{
    'name': "buz_po_portal",
    'version': '0.1',
    'category': 'Uncategorized',
    'summary': 'Module for Purchase Order Portal',
    'description': """
        - VAT detection functionality from order line taxes
        - Signature capture (draw or upload) for approval process
    """,
    'depends': ['base', 'purchase', 'mail', 'hr','website', 'portal', 'line_portal_notification'], # 'website', 'portal'
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'views/purchase_view.xml',
        'views/po_landing_page.xml',
        'views/po_signature_page.xml',
        'views/res_config_settings_views.xml',
        'wizard/purchase_approval_wizard_view.xml',
        'reports/purchase_order_report.xml',
        'reports/purchase_order_report_eng.xml',
        'reports/purchase_agreements_report.xml',
        'reports/_purchase_order_id.xml',
        'views/report_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_po_portal/static/src/scss/style.scss',
        ],
        'web.report_assets_common': [
            'buz_po_portal/static/src/scss/style.scss',
        ],
        'web.assets_frontend': [
            'buz_po_portal/static/src/js/signature_fix.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}