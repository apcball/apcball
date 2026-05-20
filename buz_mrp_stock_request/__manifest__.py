{
    "name": "MRP Stock Request (BUZ)",
    "version": "17.0.1.0.0",
    "license": "LGPL-3",
    "author": "OpenERP SA, Odoo Community, BUZ",
    "website": "https://www.odoo.com",
    "category": "Manufacturing",
    "depends": [
        "mrp",
        "stock",
        "mail",
    ],
    "data": [
        "security/mrp_stock_request_security.xml",
        "security/ir.model.access.csv",
        "data/sequence_data.xml",
        "reports/stock_request_report.xml",
        "reports/mo_close_job_report.xml",
        "views/mrp_stock_request_views.xml",
        "views/mrp_stock_request_wizard_views.xml",
        "views/mrp_stock_request_confirm_wizard_views.xml",
        "views/mrp_stock_request_allocate_multi_wizard_views.xml",
        "views/mrp_production_allocate_wizard_views.xml",
        "views/mrp_production_views.xml",
        "views/stock_picking_views.xml",
        "views/res_config_settings_views.xml",
        "views/mrp_stock_request_mark_done_wizard_views.xml",
    ],
    "demo": [
    ],
    "test": [
        "tests/test_mrp_stock_request.py",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "assets": {
        "web.report_assets_common": [
            "/buz_mrp_stock_request/static/fonts/Sarabun-Regular.ttf",
            "/buz_mrp_stock_request/static/fonts/Sarabun-Bold.ttf",
        ],
    },
}