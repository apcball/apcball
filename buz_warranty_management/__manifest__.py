{
    'name': 'Warranty Management',
    'version': '17.0.1.1.0',
    'category': 'Sales/Warranty',
    'summary': 'Complete Warranty Management System with Claims and Certificate Generation',
    'description': """
        Warranty Management System
        ===========================
        * Product-level warranty configuration
        * Manual warranty card creation from Sale Order
        * Warranty claim management (under & out-of-warranty)
        * RMA workflows with stock operations
        * Claim lines for parts and consumables tracking
        * RMA IN/OUT pickings with serial/lot support
        * Multi-product RMA IN returns with part selection
        * Replacement issue with SO integration
        * Quick invoice generation from claim lines
        * Out-of-warranty quotation generation
        * Warranty certificate and RMA slip printing
        * Configurable locations, accounts, and operation types
        * Dashboard and reporting
    """,
    'author': 'apcball',
    'website': 'https://www.buzzit.co.th',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'stock',
        'stock_account',
        'account',
        'mail',
        'uom',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_warranty_management/static/src/scss/warranty_styles.scss',
            'buz_warranty_management/static/src/scss/dashboard_indicators.scss',
            'buz_warranty_management/static/src/scss/dashboard_charts.scss',
            'buz_warranty_management/static/src/lib/chart.min.js',
            'buz_warranty_management/static/src/js/chart_simple.js',
            'buz_warranty_management/static/src/js/dashboard_charts.js',
            'buz_warranty_management/static/src/js/dashboard_auto_refresh.js',
            'buz_warranty_management/static/src/xml/dashboard_charts.xml',
        ],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/warranty_card_views.xml',
        'views/warranty_claim_views.xml',
        'views/warranty_dashboard_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/warranty_out_wizard_view.xml',
        'wizard/warranty_rma_receive_wizard_view.xml',
        'wizard/warranty_replacement_issue_wizard_view.xml',
        'wizard/warranty_invoice_wizard_view.xml',
        'report/report_warranty_certificate.xml',
        'report/report_warranty_claim_form.xml',
        'report/report_warranty_rma_slip.xml',
        'data/warranty_dashboard_cron.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
