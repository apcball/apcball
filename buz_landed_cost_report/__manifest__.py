{
    'name': 'Landed Cost Report',
    'version': '17.0.1.0.1',
    'category': 'Inventory/Reporting',
    'summary': 'Landed Cost Report with Pivot and Excel Export',
    'description': """
        Landed Cost Report module with:
        - Pivot view preview before export
        - Excel (.xlsx) export
        - Product-level landed cost breakdown
        - Single data source (SQL VIEW) shared by Pivot and Excel
    """,
    'author': 'APCBALL',
    'depends': ['stock', 'stock_landed_costs', 'product', 'base', 'report_xlsx'],
    'data': [
        'security/ir.model.access.csv',
        'views/landed_cost_report_views.xml',
        'wizard/landed_cost_report_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
