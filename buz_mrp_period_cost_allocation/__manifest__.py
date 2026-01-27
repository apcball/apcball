{
    'name': 'Manufacturing Period Cost Allocation',
    'version': '17.0.1.0.0',
    'summary': 'Allocate actual manufacturing costs to MOs on a period basis',
    'description': """
        Allocates actual manufacturing cost (DL, IDL, OH) to Manufacturing Orders (MO) 
        on a period basis, using valuation adjustment similar to Landed Cost.
        
        Key Features:
        - Period-based cost adjustment
        - Allocation based on Time, Standard Cost, or Sale Price
        - Inventory valuation adjustment
        - Optional accounting entries
    """,
    'category': 'Manufacturing',
    'author': 'APCBALL',
    'depends': ['mrp', 'stock_account', 'buz_mrp_workcenter_cost_breakdown', 'report_xlsx'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'report/mrp_period_cost_report_actions.xml',
        'report/mrp_period_cost_template.xml',
        'views/mrp_period_cost_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
