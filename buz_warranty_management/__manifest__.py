{
    'name': 'Warranty Management',
    'version': '17.0.1.4.0',
    'category': 'Sales/Warranty',
    'summary': 'Warranty cards linked to Service Receipt claims',
    'description': """
        Warranty Management System
        ===========================
        * Category-level warranty configuration (applies to all products in category)
        * Manual warranty card creation from Sale Order
        * Service Receipt claim integration (under & out-of-warranty)
        * RMA workflows with stock operations
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
        'web',
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
            'buz_warranty_management/static/src/scss/warranty_dashboard.scss',
            'buz_warranty_management/static/src/js/warranty_dashboard.js',
            'buz_warranty_management/static/src/xml/warranty_dashboard.xml',
        ],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/product_template_views.xml',
        'views/product_category_views.xml',
        'views/sale_order_views.xml',
        'views/warranty_card_views.xml',
        'views/warranty_dashboard_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'report/report_warranty_certificate.xml',
        'report/report_warranty_rma_slip.xml',
        'data/warranty_dashboard_cron.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
