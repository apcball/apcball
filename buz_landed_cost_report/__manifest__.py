{
    'name': 'Landed Cost Report',
    'version': '17.0.1.2.0',
    'category': 'Inventory/Reporting',
    'summary': 'Landed Cost Report with Pivot and Excel Export',
    'description': """
        Landed Cost Report module with:
        - Per product/move: base cost + allocated landed cost = final unit cost (company currency)
        - Cost breakdown by cost line / type / account
        - Audit: LC total vs allocation vs valuation layers
        - Pivot preview and Excel (.xlsx) export from the same SQL views
    """,
    'author': 'APCBALL',
    'depends': ['stock', 'stock_landed_costs', 'product', 'base', 'report_xlsx'],
    'data': [
        'security/ir.model.access.csv',
        'data/landed_cost_type_data.xml',
        'views/landed_cost_report_views.xml',
        'wizard/landed_cost_report_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_landed_cost_report/static/src/js/lc_export_button.js',
            'buz_landed_cost_report/static/src/xml/lc_export_button.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
