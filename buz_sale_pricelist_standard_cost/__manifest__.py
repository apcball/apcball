{
    'name': 'Sales Pricelist Standard Cost',
    'version': '17.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Calculate Sales Margin based on a Standard Cost Pricelist',
    'description': """
        Uses Pricelist as the source of Standard Cost for Sales.
        Allows Sale Pricelist to reference another Pricelist (Standard Cost Pricelist).
        Calculates Sales Margin based on Standard Cost Pricelist.
        Does NOT use product cost, FIFO, AVCO, or accounting cost.
    """,
    'author': 'Buz',
    'depends': ['sale_management', 'product'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/standard_cost_pricelist.xml',
        'views/pricelist_view.xml',
        'views/pricelist_item_view.xml',
        'views/sale_order_view.xml',
        'views/product_template_view.xml',
        'views/res_config_settings_view.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
